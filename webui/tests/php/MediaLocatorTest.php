<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

use AvianVisitors\Config;
use AvianVisitors\Support\MediaLocator;
use AvianVisitors\Support\SpeciesNames;
use AvianVisitors\Tests\Support\Runtime;
use PHPUnit\Framework\TestCase;

final class MediaLocatorTest extends TestCase
{
    private string $appDir;
    private string $songs;

    protected function setUp(): void
    {
        $this->appDir = sys_get_temp_dir() . '/av-media-' . getmypid() . '-' . uniqid();
        $this->songs = $this->appDir . '/BirdSongs';
        @mkdir($this->appDir . '/birdnet/model', 0o777, true);
        @mkdir($this->songs . '/Extracted/By_Date', 0o777, true);
    }

    protected function tearDown(): void
    {
        Runtime::rmrf($this->appDir);
    }

    private function locator(): MediaLocator
    {
        $config = new Config($this->appDir, $this->songs, $this->appDir . '/logs', 'admin', '', 'ua');
        return new MediaLocator($config, new SpeciesNames($config));
    }

    private function putMedia(string $date, string $dir, string $file, int $size): string
    {
        $full = $this->songs . '/Extracted/By_Date/' . $date . '/' . $dir;
        @mkdir($full, 0o777, true);
        file_put_contents($full . '/' . $file, str_repeat("\x00", $size));
        return $full . '/' . $file;
    }

    public function testValidSciAcceptsBinomialsAndRejectsJunk(): void
    {
        $loc = $this->locator();
        $this->assertTrue($loc->validSci('Calypte anna'));
        $this->assertTrue($loc->validSci('Aaa bbb ccc'));
        $this->assertFalse($loc->validSci('x'));
        $this->assertFalse($loc->validSci('Calypte'));
        $this->assertFalse($loc->validSci('Calypte Anna'));
        $this->assertFalse($loc->validSci('../etc/passwd'));
    }

    public function testValidFileNameEnforcesExtension(): void
    {
        $loc = $this->locator();
        $this->assertTrue($loc->validFileName('Annas_Hummingbird-95-2024-01-01.mp3', 'mp3'));
        $this->assertFalse($loc->validFileName('x.png', 'mp3'));
        $this->assertFalse($loc->validFileName('../../etc/passwd.mp3', 'mp3'));
        $this->assertTrue($loc->validFileName('spectro.png', 'png'));
        $this->assertTrue($loc->validFileName('clip.mp3', 'png'));
        $this->assertFalse($loc->validFileName('clip.wav', 'png'));
    }

    public function testFindByFileLocatesAndRejectsTooSmall(): void
    {
        $hit = $this->putMedia('2024-01-01', 'Annas_Hummingbird', 'Annas_Hummingbird-95-2024-01-01.mp3', 256);
        $this->assertSame($hit, $this->locator()->findByFile('Annas_Hummingbird-95-2024-01-01.mp3', 'mp3'));

        $this->putMedia('2024-01-02', 'House_Sparrow', 'House_Sparrow-50-2024-01-02.mp3', 10);
        $this->assertNull($this->locator()->findByFile('House_Sparrow-50-2024-01-02.mp3', 'mp3'));
    }

    public function testFindNewestBySciUsesCommonName(): void
    {
        file_put_contents($this->appDir . '/birdnet/birds.json', json_encode([[
            'sci' => 'Calypte anna',
            'com' => "Anna's Hummingbird",
        ]]));
        $this->putMedia('2024-01-01', 'Annas_Hummingbird', 'old-2024-01-01.mp3', 256);
        $newest = $this->putMedia('2024-02-01', 'Annas_Hummingbird', 'new-2024-02-01.mp3', 256);
        $this->assertSame($newest, $this->locator()->findNewestBySci('Calypte anna', 'mp3'));
    }

    public function testFindNewestBySciNullWhenNoDir(): void
    {
        $this->assertNull($this->locator()->findNewestBySci('Calypte anna', 'mp3'));
    }
}
