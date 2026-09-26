<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

use AvianVisitors\Config;
use AvianVisitors\Kernel;
use PHPUnit\Framework\Attributes\DataProvider;

final class StatusControllerTest extends SlimTestCase
{
    private const UNITS = ['recording', 'analysis', 'charts', 'stats', 'caddy', 'php-fpm', 'icecast', 'livestream'];

    private string $original = '';

    protected static function adminPassword(): string
    {
        return '';
    }

    protected function setUp(): void
    {
        parent::setUp();
        @mkdir(self::base() . '/logs', 0o777, true);
        $this->original = (string) file_get_contents(self::base() . '/app/birdnet.conf');
    }

    protected function tearDown(): void
    {
        file_put_contents(self::base() . '/app/birdnet.conf', $this->original);
        foreach (glob(self::base() . '/logs/*.log') ?: [] as $file) {
            @unlink($file);
        }
        foreach (glob(self::base() . '/BirdSongs/StreamData/*') ?: [] as $file) {
            @unlink($file);
        }
        putenv('AV_BIRDSONGS_DIR=' . self::base() . '/BirdSongs');
    }

    private function writeLog(string $unit, int $count): void
    {
        $lines = [];
        for ($i = 1; $i <= $count; $i++) {
            $lines[] = 'line ' . $i;
        }
        file_put_contents(self::base() . '/logs/' . $unit . '.log', implode("\n", $lines) . "\n");
    }

    public function testUnknownActionIs404(): void
    {
        $this->assertSame(404, $this->request('GET', '/api/status?action=reboot')['status']);
    }

    public static function rejectedUnits(): array
    {
        return [
            'not supervised' => ['sshd'],
            'traversal' => ['../../etc/passwd'],
            'case differs' => ['Recording'],
            'empty' => [''],
        ];
    }

    #[DataProvider('rejectedUnits')]
    public function testLogsRejectUnitsOutsideTheAllowlist(string $unit): void
    {
        $res = $this->json('GET', '/api/status?action=logs&unit=' . rawurlencode($unit));
        $this->assertSame(400, $res['status']);
        $this->assertSame('unit not allowed', $res['data']['error']);
        $this->assertSame(self::UNITS, $res['data']['allowed']);
    }

    public function testLogsDefaultToRecordingAndSixtyLines(): void
    {
        $this->writeLog('recording', 100);
        $res = $this->json('GET', '/api/status?action=logs');
        $this->assertSame(200, $res['status']);
        $this->assertSame('recording', $res['data']['unit']);
        $this->assertSame(60, $res['data']['lines']);
        $lines = explode("\n", $res['data']['text']);
        $this->assertCount(60, $lines);
        $this->assertSame('line 41', $lines[0]);
        $this->assertSame('line 100', $lines[59]);
    }

    public static function clampedLines(): array
    {
        return [
            'below minimum' => ['1', 10],
            'zero' => ['0', 10],
            'negative' => ['-50', 10],
            'not a number' => ['abc', 10],
            'inside range' => ['25', 25],
            'above maximum' => ['9999', 500],
        ];
    }

    #[DataProvider('clampedLines')]
    public function testLogsClampLineCount(string $requested, int $expected): void
    {
        $this->writeLog('analysis', 600);
        $res = $this->json('GET', '/api/status?action=logs&unit=analysis&lines=' . $requested);
        $this->assertSame($expected, $res['data']['lines']);
        $lines = explode("\n", $res['data']['text']);
        $this->assertCount($expected, $lines);
        $this->assertSame('line 600', end($lines));
    }

    public function testLogsForMissingFileSaySo(): void
    {
        $res = $this->json('GET', '/api/status?action=logs&unit=icecast');
        $this->assertSame(200, $res['status']);
        $this->assertStringStartsWith('(no log yet at ', $res['data']['text']);
    }

    public function testRestartRequiresPost(): void
    {
        $res = $this->json('GET', '/api/status?action=restart&unit=recording');
        $this->assertSame(405, $res['status']);
    }

    #[DataProvider('rejectedUnits')]
    public function testRestartRejectsUnitsOutsideTheAllowlist(string $unit): void
    {
        $res = $this->json('POST', '/api/status?action=restart&unit=' . rawurlencode($unit));
        $this->assertSame(400, $res['status']);
        $this->assertSame(self::UNITS, $res['data']['allowed']);
    }

    public function testRestartWithoutUnitIsRejected(): void
    {
        $this->assertSame(400, $this->request('POST', '/api/status?action=restart')['status']);
    }

    public function testSystemReportsConfSummaryWithQuotesStripped(): void
    {
        file_put_contents(
            self::base() . '/app/birdnet.conf',
            "# comment\nSITE_NAME=\"Quoted Garden\"\nCONFIDENCE = 0.8\nCADDY_PWD=hunter2\nMODEL=Perch_v2\n",
        );
        $res = $this->json('GET', '/api/status?action=system');
        $this->assertSame(200, $res['status']);
        $conf = $res['data']['conf'];
        $this->assertTrue($conf['readable']);
        $this->assertSame(
            ['SITE_NAME' => 'Quoted Garden', 'CONFIDENCE' => '0.8', 'MODEL' => 'Perch_v2'],
            $conf['values'],
        );
    }

    public function testSystemReportsDatabaseAndDisk(): void
    {
        $res = $this->json('GET', '/api/status?action=system');
        $data = $res['data'];
        $this->assertSame('no-store', $res['headers']['Cache-Control'][0]);
        $this->assertTrue($data['birds_db']['exists']);
        $this->assertGreaterThan(0, $data['birds_db']['size_bytes']);
        $this->assertSame(self::base() . '/BirdSongs', $data['disk_birds']['path']);
        $this->assertGreaterThan(0, $data['disk_birds']['total_bytes']);
        $this->assertGreaterThanOrEqual(0, $data['disk_birds']['used_pct']);
        $this->assertLessThanOrEqual(100, $data['disk_birds']['used_pct']);
        $this->assertArrayHasKey('as_of', $data);
    }

    public function testSystemReportsMemoryFromProc(): void
    {
        if (!is_readable('/proc/meminfo')) {
            $this->markTestSkipped('no /proc/meminfo');
        }
        $mem = $this->json('GET', '/api/status?action=system')['data']['mem'];
        $this->assertGreaterThan(0, $mem['total_bytes']);
        $this->assertGreaterThanOrEqual(0, $mem['used_bytes']);
        $this->assertLessThanOrEqual($mem['total_bytes'], $mem['used_bytes']);
        $this->assertGreaterThan(0, $mem['used_pct']);
        $this->assertLessThanOrEqual(100, $mem['used_pct']);
    }

    public function testSystemTemperatureIsNullOrCelsius(): void
    {
        $temp = $this->json('GET', '/api/status?action=system')['data']['temp_c'];
        if ($temp === null) {
            $this->assertFalse(is_readable('/sys/class/thermal/thermal_zone0/temp'));
            return;
        }
        $this->assertGreaterThan(-50, $temp);
        $this->assertLessThan(150, $temp);
    }

    public function testSystemReportsNewestSegment(): void
    {
        $dir = self::base() . '/BirdSongs/StreamData';
        file_put_contents($dir . '/2026-01-01-birdnet-00:00:00.wav', 'x');
        file_put_contents($dir . '/2026-01-01-birdnet-00:00:15.wav', 'x');
        file_put_contents($dir . '/notes.txt', 'x');
        $stream = $this->json('GET', '/api/status?action=system')['data']['stream_data'];
        $this->assertTrue($stream['exists']);
        $this->assertSame(2, $stream['file_count']);
        $this->assertSame('2026-01-01-birdnet-00:00:15.wav', $stream['newest_name']);
        $this->assertLessThan(120, $stream['newest_age_s']);
    }

    public function testMissingBirdsongsDirIsReported(): void
    {
        putenv('AV_BIRDSONGS_DIR=' . self::base() . '/missing');
        $this->app = Kernel::create(Config::fromEnv());
        $data = $this->json('GET', '/api/status?action=system')['data'];
        $this->assertSame(['path' => self::base() . '/missing', 'error' => 'not found'], $data['disk_birds']);
        $this->assertSame(['exists' => false], $data['stream_data']);
    }

    public function testServicesActionIsUncached(): void
    {
        $res = $this->json('GET', '/api/status?action=services');
        $this->assertSame(200, $res['status']);
        $this->assertSame('no-store', $res['headers']['Cache-Control'][0]);
        $this->assertIsArray($res['data']['services']);
        foreach (array_keys($res['data']['services']) as $unit) {
            $this->assertContains($unit, self::UNITS);
        }
    }

    public function testDiagIncludesRecentLogs(): void
    {
        $this->writeLog('recording', 30);
        $data = $this->json('GET', '/api/status')['data'];
        $lines = explode("\n", $data['recent_logs']['recording']);
        $this->assertCount(20, $lines);
        $this->assertSame('line 30', end($lines));
        $this->assertSame('', $data['recent_logs']['analysis']);
        $this->assertArrayNotHasKey('as_of', $data['system']);
    }
}
