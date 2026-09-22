<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

final class HealthTest extends SlimTestCase
{
    protected static function adminPassword(): string
    {
        return '';
    }

    public function testUpWhenDatabaseExists(): void
    {
        $res = $this->request('GET', '/health');
        $this->assertSame(200, $res['status']);
        $this->assertSame('up', $res['body']);
        $this->assertStringStartsWith('text/plain', $res['headers']['Content-Type'][0]);
    }

    public function testDegradedWhenDatabaseMissing(): void
    {
        $path = getenv('AV_APP_DIR') . '/birdnet/birds.db';
        $backup = $path . '.bak';
        rename($path, $backup);

        $res = $this->request('GET', '/health');

        rename($backup, $path);

        $this->assertSame(503, $res['status']);
        $this->assertSame('degraded', $res['body']);
    }
}
