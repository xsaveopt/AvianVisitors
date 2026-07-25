<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

final class MetricsTest extends SlimTestCase
{
    protected static function adminPassword(): string
    {
        return '';
    }

    protected function tearDown(): void
    {
        foreach (glob(self::base() . '/data/metrics/*.prom') ?: [] as $file) {
            @unlink($file);
        }
        foreach (glob(self::base() . '/BirdSongs/StreamData/*.wav') ?: [] as $file) {
            @unlink($file);
        }
    }

    private function scrape(): string
    {
        $res = $this->request('GET', '/metrics');
        $this->assertSame(200, $res['status']);
        $this->assertStringStartsWith('text/plain; version=0.0.4', $res['headers']['Content-Type'][0]);
        return $res['body'];
    }

    /** @return list<float> */
    private function values(string $body, string $name): array
    {
        $out = [];
        $m = [];
        foreach (explode("\n", $body) as $line) {
            if (preg_match('/^' . preg_quote($name, '/') . '(\{[^}]*\})?\s+(\S+)$/', $line, $m) !== 1) {
                continue;
            }
            $out[] = (float) $m[2];
        }
        return $out;
    }

    private function value(string $body, string $name): float
    {
        $values = $this->values($body, $name);
        $this->assertCount(1, $values, "expected exactly one sample of {$name}");
        return $values[0];
    }

    public function testEveryFamilyIsTypedAndHelped(): void
    {
        $body = $this->scrape();
        $types = [];
        $helps = [];
        $seen = [];
        $m = [];
        foreach (explode("\n", $body) as $line) {
            if ($line === '') {
                continue;
            }
            if (preg_match('/^# TYPE (\S+) (\S+)$/', $line, $m) === 1) {
                $this->assertArrayNotHasKey($m[1], $types, "duplicate TYPE for {$m[1]}");
                $types[$m[1]] = $m[2];
                continue;
            }
            if (preg_match('/^# HELP (\S+) /', $line, $m) === 1) {
                $this->assertArrayNotHasKey($m[1], $helps, "duplicate HELP for {$m[1]}");
                $helps[$m[1]] = true;
                continue;
            }
            $this->assertSame(
                1,
                preg_match('/^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})? (\S+)$/', $line, $m),
                "malformed line: {$line}",
            );
            $seen[preg_replace('/_(bucket|sum|count)$/', '', $m[1])] = true;
        }

        $this->assertNotSame([], $types);
        foreach (array_keys($seen) as $name) {
            $this->assertArrayHasKey($name, $types, "sample {$name} has no TYPE");
            $this->assertArrayHasKey($name, $helps, "sample {$name} has no HELP");
        }
    }

    public function testDetectionCountersMatchTheDatabase(): void
    {
        $body = $this->scrape();
        $species = $this->values($body, 'avianvisitors_detections_total');
        $this->assertCount(4, $species);
        $this->assertSame(7.0, array_sum($species));
        $this->assertSame(4.0, $this->value($body, 'avianvisitors_species_lifelist'));
        $this->assertSame(1.0, $this->value($body, 'avianvisitors_database_present'));
        $this->assertStringContainsString(
            'avianvisitors_detections_total{sci="Calypte anna",com="Anna\'s Hummingbird"}',
            $body,
        );
    }

    public function testConfidenceHistogramIsCumulativeAndComplete(): void
    {
        $body = $this->scrape();
        $this->assertSame(7.0, $this->value($body, 'avianvisitors_detection_confidence_count'));
        $buckets = $this->values($body, 'avianvisitors_detection_confidence_bucket');
        $this->assertNotSame([], $buckets);
        $this->assertSame(7.0, $buckets[count($buckets) - 1]);
        $previous = 0.0;
        foreach ($buckets as $value) {
            $this->assertGreaterThanOrEqual($previous, $value);
            $previous = $value;
        }
    }

    public function testLagIsDerivedFromTheNewestDetection(): void
    {
        $body = $this->scrape();
        $last = $this->value($body, 'avianvisitors_last_detection_timestamp_seconds');
        $this->assertGreaterThan(0, $last);
        $this->assertLessThan(120, $this->value($body, 'avianvisitors_analysis_lag_seconds'));
    }

    public function testPendingSegmentsAreCounted(): void
    {
        $dir = self::base() . '/BirdSongs/StreamData';
        file_put_contents($dir . '/2026-01-01-birdnet-00:00:00.wav', str_repeat('x', 32));
        file_put_contents($dir . '/2026-01-01-birdnet-00:00:15.wav', str_repeat('x', 16));
        file_put_contents($dir . '/analyzing_now.txt', $dir . '/2026-01-01-birdnet-00:00:00.wav');

        $body = $this->scrape();
        $this->assertSame(2.0, $this->value($body, 'avianvisitors_segments_pending'));
        $this->assertSame(48.0, $this->value($body, 'avianvisitors_segments_pending_bytes'));
        $this->assertLessThan(120, $this->value($body, 'avianvisitors_analyzing_now_age_seconds'));
        @unlink($dir . '/analyzing_now.txt');
    }

    public function testNoPendingSegmentsReportsZeroAndSkipsAges(): void
    {
        $body = $this->scrape();
        $this->assertSame(0.0, $this->value($body, 'avianvisitors_segments_pending'));
        $this->assertSame([], $this->values($body, 'avianvisitors_segment_oldest_age_seconds'));
    }

    public function testTextfileCollectorIsAppended(): void
    {
        file_put_contents(
            self::base() . '/data/metrics/analysis.prom',
            "# HELP avianvisitors_analysis_duration_seconds Model wall time.\n"
            . "# TYPE avianvisitors_analysis_duration_seconds gauge\n"
            . "avianvisitors_analysis_duration_seconds 1.25\n",
        );

        $body = $this->scrape();
        $this->assertSame(1.25, $this->value($body, 'avianvisitors_analysis_duration_seconds'));
        $this->assertSame(0.0, $this->value($body, 'avianvisitors_textfile_read_errors'));
    }

    public function testStorageMetricsCoverTheDataVolume(): void
    {
        $body = $this->scrape();
        $this->assertSame(1.0, $this->value($body, 'avianvisitors_data_writable'));
        $this->assertGreaterThan(0, $this->value($body, 'avianvisitors_data_disk_total_bytes'));
        $this->assertGreaterThan(0, $this->value($body, 'avianvisitors_database_bytes'));
    }
}
