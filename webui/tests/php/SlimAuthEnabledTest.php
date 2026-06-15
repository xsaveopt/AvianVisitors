<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

use PHPUnit\Framework\Attributes\DataProvider;

final class SlimAuthEnabledTest extends SlimTestCase
{
    private const USER = 'admin';
    private const PASS = 's3cret-pw';

    protected static function adminPassword(): string
    {
        return self::PASS;
    }

    public static function protectedEndpoints(): array
    {
        return [
            'menu' => ['/api/menu'],
            'config' => ['/api/config'],
            'status' => ['/api/status?action=diag'],
            'recording' => ['/api/recording?sci=' . rawurlencode('Calypte anna')],
            'spectrogram' => ['/api/spectrogram?sci=' . rawurlencode('Calypte anna')],
        ];
    }

    public static function publicEndpoints(): array
    {
        return [
            'stats' => ['/api/stats'],
            'illustration' => ['/api/illustration?sci=' . rawurlencode('Calypte anna')],
        ];
    }

    #[DataProvider('protectedEndpoints')]
    public function testProtectedRejectsAnonymous(string $path): void
    {
        $this->assertSame(401, $this->request('GET', $path)['status']);
    }

    #[DataProvider('protectedEndpoints')]
    public function testProtectedRejectsWrongPassword(string $path): void
    {
        $res = $this->request('GET', $path, self::basic(self::USER, 'wrong'));
        $this->assertSame(401, $res['status']);
    }

    #[DataProvider('protectedEndpoints')]
    public function testProtectedAllowsCorrectPassword(string $path): void
    {
        $res = $this->request('GET', $path, self::basic(self::USER, self::PASS));
        $this->assertSame(200, $res['status']);
    }

    #[DataProvider('publicEndpoints')]
    public function testPublicStaysOpen(string $path): void
    {
        $this->assertSame(200, $this->request('GET', $path)['status']);
    }

    public function testRejectDoesNotSendBrowserChallenge(): void
    {
        $res = $this->request('GET', '/api/menu');
        $this->assertSame(401, $res['status']);
        $this->assertArrayNotHasKey('WWW-Authenticate', $res['headers']);
    }
}
