<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

use AvianVisitors\Support\Conf;
use PHPUnit\Framework\TestCase;

final class ConfTest extends TestCase
{
    private string $path;

    protected function setUp(): void
    {
        $this->path = sys_get_temp_dir() . '/av-conf-' . getmypid() . '-' . uniqid() . '.conf';
    }

    protected function tearDown(): void
    {
        @unlink($this->path);
    }

    private function seed(string $contents): Conf
    {
        file_put_contents($this->path, $contents);
        return new Conf($this->path);
    }

    public function testReadStripsQuotesAndSkipsCommentsAndBlanks(): void
    {
        $conf = $this->seed("# comment\n\nSITE_NAME=\"Test Garden\"\nCONFIDENCE=0.7\nRTSP_STREAM=\n");
        $this->assertSame(['SITE_NAME' => 'Test Garden', 'CONFIDENCE' => '0.7', 'RTSP_STREAM' => ''], $conf->read());
    }

    public function testReadMissingFileReturnsEmpty(): void
    {
        $this->assertSame([], (new Conf('/no/such/file.conf'))->read());
    }

    public function testWriteUpdatesExistingAndPreservesOthers(): void
    {
        $conf = $this->seed("SITE_NAME=\"Test Garden\"\nCONFIDENCE=0.7\n");
        $this->assertTrue($conf->write(['CONFIDENCE' => 0.9]));
        $read = $conf->read();
        $this->assertSame('0.9', $read['CONFIDENCE']);
        $this->assertSame('Test Garden', $read['SITE_NAME']);
    }

    public function testWriteAppendsNewKey(): void
    {
        $conf = $this->seed("CONFIDENCE=0.7\n");
        $conf->write(['NEW_KEY' => 'value']);
        $this->assertSame('value', $conf->read()['NEW_KEY']);
    }

    public function testWriteQuotesValuesWithSpacesAndEmpty(): void
    {
        $conf = $this->seed("X=1\n");
        $conf->write(['SITE_NAME' => 'My Garden', 'EMPTY' => '', 'SIMPLE' => 'v1.2_a/b+c-d']);
        $raw = file_get_contents($this->path);
        $this->assertStringContainsString('SITE_NAME="My Garden"', $raw);
        $this->assertStringContainsString('EMPTY=""', $raw);
        $this->assertStringContainsString('SIMPLE=v1.2_a/b+c-d', $raw);
    }

    public function testWriteReturnsFalseWhenUnwritable(): void
    {
        $this->assertFalse((new Conf('/no/such/dir/birdnet.conf'))->write(['A' => 'b']));
    }
}
