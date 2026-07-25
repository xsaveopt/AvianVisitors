<?php

declare(strict_types=1);

namespace AvianVisitors\Actions;

use AvianVisitors\Config;
use AvianVisitors\Database;
use AvianVisitors\Support\Exposition;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

final class MetricsController
{
    private const PREFIX = 'avianvisitors_';

    private const CONFIDENCE_BUCKETS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99];

    private const UNITS = [
        'recording',
        'analysis',
        'charts',
        'stats',
        'caddy',
        'php-fpm',
        'icecast',
        'livestream',
    ];

    private const SUPERVISORCTL = '/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf';

    private const CGROUP = '/sys/fs/cgroup';

    public function __construct(
        private readonly Config $config,
        private readonly Database $db,
    ) {}

    public function __invoke(Request $request, Response $response): Response
    {
        $started = microtime(true);
        $exposition = new Exposition();

        $this->detections($exposition);
        $this->pipeline($exposition);
        $this->storage($exposition);
        $this->audio($exposition);
        $this->services($exposition);
        $this->container($exposition);
        $this->textfiles($exposition);

        $exposition->single(
            self::PREFIX . 'scrape_duration_seconds',
            'gauge',
            'Time this exporter spent building the response.',
            microtime(true) - $started,
        );

        $response->getBody()->write($exposition->render());
        return $response->withHeader('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')->withHeader(
            'Cache-Control',
            'no-store',
        );
    }

    private function detections(Exposition $exposition): void
    {
        if (!$this->db->exists()) {
            $exposition->single(
                self::PREFIX . 'database_present',
                'gauge',
                'Whether the detections database exists.',
                0,
            );
            return;
        }
        $exposition->single(self::PREFIX . 'database_present', 'gauge', 'Whether the detections database exists.', 1);

        $samples = [];
        foreach ($this->db->rows(
            'SELECT Sci_Name AS sci, Com_Name AS com, COUNT(*) AS n FROM detections GROUP BY Sci_Name, Com_Name',
        ) as $row) {
            $samples[] = [['sci' => (string) $row['sci'], 'com' => (string) $row['com']], (int) $row['n']];
        }
        $exposition->series(
            self::PREFIX . 'detections_total',
            'counter',
            'Detections ever written to the database, by species.',
            $samples,
        );

        $exposition->single(
            self::PREFIX . 'species_lifelist',
            'gauge',
            'Distinct species ever detected.',
            (int) $this->db->value('SELECT COUNT(DISTINCT Sci_Name) FROM detections'),
        );
        $exposition->single(
            self::PREFIX . 'species_active_24h',
            'gauge',
            'Distinct species detected in the last 24 hours.',
            (int) $this->db->value(
                "SELECT COUNT(DISTINCT Sci_Name) FROM detections WHERE Date || ' ' || Time >= DATETIME('now','localtime','-1 day')",
            ),
        );
        $exposition->single(
            self::PREFIX . 'detections_24h',
            'gauge',
            'Detections in the last 24 hours.',
            (int) $this->db->value(
                "SELECT COUNT(*) FROM detections WHERE Date || ' ' || Time >= DATETIME('now','localtime','-1 day')",
            ),
        );

        $last = $this->epoch('MAX');
        $first = $this->epoch('MIN');
        $exposition->single(
            self::PREFIX . 'last_detection_timestamp_seconds',
            'gauge',
            'Unix time of the most recent detection.',
            $last,
        );
        $exposition->single(
            self::PREFIX . 'first_detection_timestamp_seconds',
            'gauge',
            'Unix time of the oldest detection on record.',
            $first,
        );
        $exposition->single(
            self::PREFIX . 'analysis_lag_seconds',
            'gauge',
            'Seconds since the most recent detection was written.',
            $last === null ? null : max(0, time() - $last),
        );

        $this->confidence($exposition);
    }

    private function confidence(Exposition $exposition): void
    {
        $select = [];
        foreach (self::CONFIDENCE_BUCKETS as $i => $bucket) {
            $select[] = sprintf('SUM(CASE WHEN Confidence <= %.4F THEN 1 ELSE 0 END) AS b%d', $bucket, $i);
        }
        $select[] = 'COUNT(*) AS n';
        $select[] = 'COALESCE(SUM(Confidence), 0) AS s';
        $row = $this->db->one('SELECT ' . implode(', ', $select) . ' FROM detections');
        if ($row === null) {
            return;
        }
        $cumulative = [];
        foreach (self::CONFIDENCE_BUCKETS as $i => $bucket) {
            $cumulative[rtrim(rtrim(sprintf('%.4F', $bucket), '0'), '.')] = self::toInt($row['b' . $i]);
        }
        $exposition->histogram(
            self::PREFIX . 'detection_confidence',
            'Distribution of detection confidence scores.',
            $cumulative,
            self::toInt($row['n']),
            self::toFloat($row['s']),
        );
    }

    private function epoch(string $aggregate): ?int
    {
        /** @var mixed $value */
        $value = $this->db->value("SELECT STRFTIME('%s', {$aggregate}(Date || ' ' || Time), 'utc') FROM detections");
        return is_numeric($value) ? (int) $value : null;
    }

    private static function toInt(mixed $value): int
    {
        return is_numeric($value) ? (int) $value : 0;
    }

    private static function toFloat(mixed $value): float
    {
        return is_numeric($value) ? (float) $value : 0.0;
    }

    private function pipeline(Exposition $exposition): void
    {
        $dir = $this->config->streamDir();
        $files = is_dir($dir) ? (glob($dir . '/*.wav') ?: []) : [];
        $now = time();
        $bytes = 0;
        $oldest = null;
        $newest = null;
        foreach ($files as $file) {
            $bytes += (int) @filesize($file);
            $mtime = (int) @filemtime($file);
            if ($mtime <= 0) {
                continue;
            }
            $oldest = $oldest === null ? $mtime : min($oldest, $mtime);
            $newest = $newest === null ? $mtime : max($newest, $mtime);
        }

        $exposition->single(
            self::PREFIX . 'segments_pending',
            'gauge',
            'Recorded wav segments waiting for analysis.',
            count($files),
        );
        $exposition->single(
            self::PREFIX . 'segments_pending_bytes',
            'gauge',
            'Total size of the wav segments waiting for analysis.',
            $bytes,
        );
        $exposition->single(
            self::PREFIX . 'segment_oldest_age_seconds',
            'gauge',
            'Age of the oldest unanalysed wav segment.',
            $oldest === null ? null : max(0, $now - $oldest),
        );
        $exposition->single(
            self::PREFIX . 'segment_newest_age_seconds',
            'gauge',
            'Age of the newest wav segment; grows when the recorder stops writing.',
            $newest === null ? null : max(0, $now - $newest),
        );

        $marker = $this->config->analyzingNowPath();
        $mtime = is_file($marker) ? (int) @filemtime($marker) : 0;
        $exposition->single(
            self::PREFIX . 'analyzing_now_age_seconds',
            'gauge',
            'Age of the analyser progress marker; a stuck file keeps this climbing.',
            $mtime > 0 ? max(0, $now - $mtime) : null,
        );
    }

    private function storage(Exposition $exposition): void
    {
        $data = $this->config->dataDir;
        if (is_dir($data)) {
            $free = @disk_free_space($data);
            $total = @disk_total_space($data);
            $exposition->single(
                self::PREFIX . 'data_disk_free_bytes',
                'gauge',
                'Free space on the data volume.',
                is_float($free) ? (int) $free : null,
            );
            $exposition->single(
                self::PREFIX . 'data_disk_total_bytes',
                'gauge',
                'Total size of the data volume.',
                is_float($total) ? (int) $total : null,
            );
            $exposition->single(
                self::PREFIX . 'data_writable',
                'gauge',
                'Whether the data volume still accepts writes; 0 means a read-only remount.',
                $this->probeWrite($data) ? 1 : 0,
            );
        }

        $db = $this->config->dbPath();
        $exposition->single(
            self::PREFIX . 'database_bytes',
            'gauge',
            'Size of the detections database.',
            is_file($db) ? (int) filesize($db) : null,
        );
    }

    private function probeWrite(string $dir): bool
    {
        $probe = $dir . '/.av-metrics-probe';
        if (@file_put_contents($probe, '') === false) {
            return false;
        }
        @unlink($probe);
        return true;
    }

    private function audio(Exposition $exposition): void
    {
        $states = [];
        $rates = [];
        $channels = [];
        $info = [];
        $m = [];
        $s = [];
        $r = [];
        $c = [];
        $f = [];
        foreach (glob('/proc/asound/card*/pcm*c/sub*/status') ?: [] as $path) {
            if (preg_match('#/card(\d+)/pcm(\d+)c/#', $path, $m) !== 1) {
                continue;
            }
            $labels = ['card' => $m[1], 'device' => $m[2]];
            $status = (string) @file_get_contents($path);
            $running = preg_match('/^state:\s*(\S+)/m', $status, $s) === 1 && strtoupper($s[1]) === 'RUNNING';
            $states[] = [$labels, $running ? 1 : 0];

            $params = (string) @file_get_contents(dirname($path) . '/hw_params');
            if (preg_match('/^rate:\s*(\d+)/m', $params, $r) === 1) {
                $rates[] = [$labels, (int) $r[1]];
            }
            if (preg_match('/^channels:\s*(\d+)/m', $params, $c) === 1) {
                $channels[] = [$labels, (int) $c[1]];
            }
            if (preg_match('/^format:\s*(\S+)/m', $params, $f) === 1) {
                $info[] = [$labels + ['format' => $f[1]], 1];
            }
        }

        $exposition->series(
            self::PREFIX . 'alsa_capture_running',
            'gauge',
            'Whether the ALSA capture stream is in the RUNNING state.',
            $states,
        );
        $exposition->series(
            self::PREFIX . 'alsa_capture_rate_hz',
            'gauge',
            'Sample rate the capture device negotiated; a mismatch with SAMPLERATE hurts detection.',
            $rates,
        );
        $exposition->series(
            self::PREFIX . 'alsa_capture_channels',
            'gauge',
            'Channel count the capture device negotiated.',
            $channels,
        );
        $exposition->series(
            self::PREFIX . 'alsa_capture_info',
            'gauge',
            'Sample format of the open capture stream.',
            $info,
        );
    }

    private function services(Exposition $exposition): void
    {
        $up = [];
        $uptime = [];
        $cpu = [];
        $rss = [];
        $p = [];
        $m = [];
        foreach (explode("\n", $this->shell(self::SUPERVISORCTL . ' status')) as $line) {
            if (preg_match('/^(\S+)\s+(\S+)\s*(.*)$/', $line, $m) !== 1) {
                continue;
            }
            if (!in_array($m[1], self::UNITS, true)) {
                continue;
            }
            $labels = ['name' => $m[1]];
            $running = strtoupper($m[2]) === 'RUNNING';
            $up[] = [$labels, $running ? 1 : 0];
            if (!$running) {
                continue;
            }
            $detail = $m[3];
            $seconds = $this->uptimeSeconds($detail);
            if ($seconds !== null) {
                $uptime[] = [$labels, $seconds];
            }
            if (preg_match('/pid (\d+)/', $detail, $p) !== 1) {
                continue;
            }
            $pid = (int) $p[1];
            $seconds = $this->processCpu($pid);
            if ($seconds !== null) {
                $cpu[] = [$labels, $seconds];
            }
            $bytes = $this->processRss($pid);
            if ($bytes !== null) {
                $rss[] = [$labels, $bytes];
            }
        }

        $exposition->series(self::PREFIX . 'service_up', 'gauge', 'Whether a supervised service is running.', $up);
        $exposition->series(
            self::PREFIX . 'service_uptime_seconds',
            'gauge',
            'How long a supervised service has been running; resets reveal crash loops.',
            $uptime,
        );
        $exposition->series(
            self::PREFIX . 'process_cpu_seconds_total',
            'counter',
            'CPU time consumed by a supervised service.',
            $cpu,
        );
        $exposition->series(
            self::PREFIX . 'process_resident_memory_bytes',
            'gauge',
            'Resident memory of a supervised service.',
            $rss,
        );
    }

    private function uptimeSeconds(string $detail): ?int
    {
        $m = [];
        if (preg_match('/uptime\s+(?:(\d+) days?,\s*)?(\d+):(\d+):(\d+)/', $detail, $m) !== 1) {
            return null;
        }
        return ((int) ($m[1] ?: 0) * 86400) + ((int) $m[2] * 3600) + ((int) $m[3] * 60) + (int) $m[4];
    }

    private function processCpu(int $pid): ?float
    {
        $stat = @file_get_contents('/proc/' . $pid . '/stat');
        if ($stat === false) {
            return null;
        }
        $close = strrpos($stat, ') ');
        if ($close === false) {
            return null;
        }
        $fields = preg_split('/\s+/', trim(substr($stat, $close + 2))) ?: [];
        if (count($fields) < 13) {
            return null;
        }
        $ticks = self::toFloat($fields[11]) + self::toFloat($fields[12]);
        return $ticks / 100;
    }

    private function processRss(int $pid): ?int
    {
        $statm = @file_get_contents('/proc/' . $pid . '/statm');
        if ($statm === false) {
            return null;
        }
        $fields = preg_split('/\s+/', trim($statm)) ?: [];
        if (count($fields) < 2) {
            return null;
        }
        return self::toInt($fields[1]) * 4096;
    }

    private function container(Exposition $exposition): void
    {
        $exposition->single(
            self::PREFIX . 'container_memory_bytes',
            'gauge',
            'Memory currently charged to the container cgroup.',
            $this->cgroupValue('memory.current'),
        );
        $exposition->single(
            self::PREFIX . 'container_memory_peak_bytes',
            'gauge',
            'High water mark of container memory usage.',
            $this->cgroupValue('memory.peak'),
        );
        $exposition->single(
            self::PREFIX . 'container_memory_limit_bytes',
            'gauge',
            'Memory limit of the container cgroup; absent when unlimited.',
            $this->cgroupValue('memory.max'),
        );
        $exposition->single(
            self::PREFIX . 'container_pids',
            'gauge',
            'Processes running inside the container cgroup.',
            $this->cgroupValue('pids.current'),
        );

        $stat = @file_get_contents(self::CGROUP . '/cpu.stat');
        if ($stat === false) {
            return;
        }
        $keys = [
            'usage_usec' => [
                self::PREFIX . 'container_cpu_seconds_total',
                'counter',
                'CPU time used by the container cgroup.',
                1000000,
            ],
            'throttled_usec' => [
                self::PREFIX . 'container_cpu_throttled_seconds_total',
                'counter',
                'CPU time the container was held back by its quota.',
                1000000,
            ],
            'nr_throttled' => [
                self::PREFIX . 'container_cpu_throttle_events_total',
                'counter',
                'Periods in which the container hit its CPU quota.',
                1,
            ],
        ];
        $m = [];
        foreach ($keys as $key => [$name, $type, $help, $divisor]) {
            if (preg_match('/^' . $key . '\s+(\d+)$/m', $stat, $m) !== 1) {
                continue;
            }
            $value = $divisor === 1 ? self::toInt($m[1]) : self::toFloat($m[1]) / $divisor;
            $exposition->single($name, $type, $help, $value);
        }
    }

    private function cgroupValue(string $file): ?int
    {
        $raw = @file_get_contents(self::CGROUP . '/' . $file);
        if ($raw === false) {
            return null;
        }
        $raw = trim($raw);
        return is_numeric($raw) ? (int) $raw : null;
    }

    private function textfiles(Exposition $exposition): void
    {
        $dir = $this->config->metricsDir();
        if (!is_dir($dir)) {
            return;
        }
        $files = glob($dir . '/*.prom') ?: [];
        sort($files);
        $failed = 0;
        foreach ($files as $file) {
            $text = @file_get_contents($file);
            if ($text === false) {
                $failed++;
                continue;
            }
            $exposition->raw($text);
        }
        $exposition->single(
            self::PREFIX . 'textfile_read_errors',
            'gauge',
            'Textfile collector files that could not be read this scrape.',
            $failed,
        );
    }

    private function shell(string $cmd): string
    {
        $rc = 0;
        $out = [];
        exec($cmd . ' 2>&1', $out, $rc);
        return implode("\n", $out);
    }
}
