<?php

declare(strict_types=1);

namespace AvianVisitors\Actions;

use AvianVisitors\Config;
use AvianVisitors\Support\Json;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

final class StatusController
{
    private const ALLOWED_UNITS = [
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

    public function __construct(
        private readonly Config $config,
    ) {}

    public function __invoke(Request $request, Response $response): Response
    {
        $action = (string) ($request->getQueryParams()['action'] ?? 'diag');

        return match ($action) {
            'system' => Json::write($response->withHeader('Cache-Control', 'no-store'), $this->system()),
            'services' => Json::write($response->withHeader('Cache-Control', 'no-store'), [
                'services' => $this->services(),
                'as_of' => date('c'),
            ]),
            'logs' => $this->logs($request, $response),
            'restart' => $this->restart($request, $response),
            'diag' => Json::write($response->withHeader('Cache-Control', 'no-store'), $this->diag()),
            default => Json::error($response, 'unknown action', 404),
        };
    }

    private function system(): array
    {
        return [
            'uptime' => $this->uptime(),
            'mem' => $this->mem(),
            'disk_root' => $this->disk('/'),
            'disk_birds' => $this->disk($this->config->birdsongsDir),
            'temp_c' => $this->temp(),
            'audio' => $this->audio(),
            'stream_data' => $this->streamData(),
            'birds_db' => $this->dbAge(),
            'conf' => $this->confSummary(),
            'hostname' => trim($this->shell('hostname')),
            'kernel' => trim($this->shell('uname -r')),
            'as_of' => date('c'),
        ];
    }

    private function diag(): array
    {
        $recentLogs = [];
        foreach (['recording', 'analysis'] as $u) {
            $f = $this->config->logsDir . '/' . $u . '.log';
            $recentLogs[$u] = is_readable($f) ? trim($this->shell('tail -n 20 ' . escapeshellarg($f))) : '';
        }
        $system = $this->system();
        unset($system['as_of']);
        return [
            'system' => $system,
            'services' => $this->services(),
            'recent_logs' => $recentLogs,
            'as_of' => date('c'),
        ];
    }

    private function logs(Request $request, Response $response): Response
    {
        $params = $request->getQueryParams();
        $unit = (string) ($params['unit'] ?? 'recording');
        $lines = max(10, min(500, (int) ($params['lines'] ?? 60)));
        if (!in_array($unit, self::ALLOWED_UNITS, true)) {
            return Json::write($response, ['error' => 'unit not allowed', 'allowed' => self::ALLOWED_UNITS], 400);
        }
        $file = $this->config->logsDir . '/' . $unit . '.log';
        $text = is_readable($file)
            ? $this->shell('tail -n ' . $lines . ' ' . escapeshellarg($file))
            : '(no log yet at ' . $file . ')';
        return Json::write($response, ['unit' => $unit, 'lines' => $lines, 'text' => $text]);
    }

    private function restart(Request $request, Response $response): Response
    {
        if ($request->getMethod() !== 'POST') {
            return Json::error($response, 'POST required', 405);
        }
        $unit = (string) ($request->getQueryParams()['unit'] ?? '');
        if (!in_array($unit, self::ALLOWED_UNITS, true)) {
            return Json::write($response, ['error' => 'unit not allowed', 'allowed' => self::ALLOWED_UNITS], 400);
        }
        $rc = 0;
        $out = [];
        exec(self::SUPERVISORCTL . ' restart ' . escapeshellarg($unit) . ' 2>&1', $out, $rc);
        return Json::write($response, [
            'unit' => $unit,
            'ok' => $rc === 0,
            'rc' => $rc,
            'out' => implode("\n", $out),
        ]);
    }

    private function services(): array
    {
        $raw = $this->shell(self::SUPERVISORCTL . ' status');
        $out = [];
        foreach (explode("\n", $raw) as $line) {
            if (!preg_match('/^(\S+)\s+(\S+)\s*(.*)$/', $line, $m)) {
                continue;
            }
            if (!in_array($m[1], self::ALLOWED_UNITS, true)) {
                continue;
            }
            $state = strtoupper($m[2]);
            $out[$m[1]] = [
                'active' => $state === 'RUNNING' ? 'active' : strtolower($state),
                'enabled' => 'managed',
                'since' => $m[3] !== '' ? $m[3] : null,
            ];
        }
        return $out;
    }

    private function uptime(): array
    {
        $up = @file_get_contents('/proc/uptime');
        $sec = $up ? (float) explode(' ', trim($up))[0] : 0;
        return [
            'seconds' => $sec,
            'pretty' => $this->humanDuration((int) $sec),
            'load' => sys_getloadavg(),
            'now' => date('c'),
        ];
    }

    private function humanDuration(int $s): string
    {
        $d = intdiv($s, 86400);
        $s -= $d * 86400;
        $h = intdiv($s, 3600);
        $s -= $h * 3600;
        $m = intdiv($s, 60);
        $parts = [];
        if ($d) {
            $parts[] = $d . 'd';
        }
        if ($h) {
            $parts[] = $h . 'h';
        }
        if ($m && !$d) {
            $parts[] = $m . 'm';
        }
        return $parts ? implode(' ', $parts) : '<1m';
    }

    private function mem(): array
    {
        $info = @file_get_contents('/proc/meminfo') ?: '';
        preg_match('/MemTotal:\s+(\d+)/', $info, $t);
        preg_match('/MemAvailable:\s+(\d+)/', $info, $a);
        $tot = isset($t[1]) ? (int) $t[1] * 1024 : 0;
        $avail = isset($a[1]) ? (int) $a[1] * 1024 : 0;
        $used = $tot - $avail;
        return [
            'total_bytes' => $tot,
            'used_bytes' => $used,
            'used_pct' => $tot ? round(($used / $tot) * 100, 1) : 0,
        ];
    }

    private function disk(string $path): array
    {
        if (!is_dir($path)) {
            return ['path' => $path, 'error' => 'not found'];
        }
        $tot = @disk_total_space($path);
        $free = @disk_free_space($path);
        if (!$tot) {
            return ['path' => $path, 'error' => 'stat failed'];
        }
        return [
            'path' => $path,
            'total_bytes' => (int) $tot,
            'free_bytes' => (int) $free,
            'used_pct' => round((($tot - $free) / $tot) * 100, 1),
        ];
    }

    private function temp(): ?float
    {
        $f = '/sys/class/thermal/thermal_zone0/temp';
        if (!is_readable($f)) {
            return null;
        }
        $raw = trim((string) @file_get_contents($f));
        return $raw === '' ? null : round((int) $raw / 1000, 1);
    }

    private function audio(): array
    {
        $cards = [];
        foreach (explode("\n", $this->shell('arecord -l')) as $line) {
            if (preg_match('/^card \d+:/', $line)) {
                $cards[] = trim($line);
            }
        }
        $usb = $this->shell('lsusb');
        return [
            'arecord_l' => $cards,
            'usb' => array_values(array_filter(explode("\n", $usb), static function ($l) {
                return (
                    $l !== ''
                    && (
                        stripos($l, 'audio') !== false
                        || stripos($l, 'microphone') !== false
                        || stripos($l, 'mic') !== false
                    )
                );
            })),
        ];
    }

    private function streamData(): array
    {
        $dir = $this->config->streamDir();
        if (!is_dir($dir)) {
            return ['exists' => false];
        }
        $files = @scandir($dir, SCANDIR_SORT_DESCENDING) ?: [];
        $wav = array_values(array_filter($files, static function ($f) {
            return $f !== '.' && $f !== '..' && preg_match('/\.(wav|mp3|raw)$/i', $f);
        }));
        $newestAge = null;
        if (count($wav) > 0) {
            $newestAge = time() - (int) @filemtime("{$dir}/" . $wav[0]);
        }
        return [
            'exists' => true,
            'file_count' => count($wav),
            'newest_age_s' => $newestAge,
            'newest_name' => $wav[0] ?? null,
        ];
    }

    private function dbAge(): array
    {
        $db = $this->config->dbPath();
        if (!is_file($db)) {
            return ['exists' => false];
        }
        return [
            'exists' => true,
            'size_bytes' => (int) filesize($db),
            'modified_s' => time() - (int) filemtime($db),
            'mtime' => date('c', (int) filemtime($db)),
        ];
    }

    private function confSummary(): array
    {
        $p = $this->config->confPath();
        if (!is_readable($p)) {
            return ['readable' => false];
        }
        $keys = [
            'CONFIDENCE',
            'SENSITIVITY',
            'OVERLAP',
            'REC_CARD',
            'LATITUDE',
            'LONGITUDE',
            'MODEL',
            'SITE_NAME',
            'RTSP_STREAM',
        ];
        $vals = [];
        foreach (file($p, FILE_IGNORE_NEW_LINES) as $line) {
            if (!$line || $line[0] === '#') {
                continue;
            }
            if (preg_match('/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$/i', $line, $m) && in_array($m[1], $keys, true)) {
                $v = trim($m[2]);
                if (strlen($v) >= 2 && $v[0] === '"' && substr($v, -1) === '"') {
                    $v = substr($v, 1, -1);
                }
                $vals[$m[1]] = $v;
            }
        }
        return ['readable' => true, 'values' => $vals];
    }

    private function shell(string $cmd): string
    {
        $rc = 0;
        $out = [];
        exec($cmd . ' 2>&1', $out, $rc);
        return implode("\n", $out);
    }
}
