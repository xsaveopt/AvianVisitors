<?php

declare(strict_types=1);

namespace AvianVisitors;

final class Config
{
    public function __construct(
        public readonly string $appDir,
        public readonly string $birdsongsDir,
        public readonly string $logsDir,
        public readonly string $adminUser,
        #[\SensitiveParameter]
        public readonly string $adminPassword,
        public readonly string $userAgent,
    ) {}

    public static function fromEnv(): self
    {
        $appDir = self::env('AV_APP_DIR', '/home/birdnet/BirdNET-Pi');
        $birdsongs = self::env('AV_BIRDSONGS_DIR', dirname($appDir) . '/BirdSongs');

        return new self(
            appDir: $appDir,
            birdsongsDir: $birdsongs,
            logsDir: self::env('AV_LOGS_DIR', '/data/logs'),
            adminUser: self::env('AV_ADMIN_USER', 'admin'),
            adminPassword: self::env('AV_ADMIN_PASSWORD', ''),
            userAgent: self::env('AV_USER_AGENT', 'AvianVisitors/1.0 (+https://github.com/Twarner491/AvianVisitors)'),
        );
    }

    private static function env(string $key, string $default): string
    {
        $value = getenv($key);
        return $value === false || $value === '' ? $default : $value;
    }

    public function dbPath(): string
    {
        return $this->appDir . '/birdnet/birds.db';
    }

    public function confPath(): string
    {
        return $this->appDir . '/birdnet.conf';
    }

    public function byDateDir(): string
    {
        return $this->birdsongsDir . '/Extracted/By_Date';
    }

    public function birdsJsonPath(): string
    {
        return $this->appDir . '/birdnet/birds.json';
    }

    public function labelsPath(): string
    {
        return $this->appDir . '/birdnet/model/labels.txt';
    }

    public function illustrationsDir(): string
    {
        return $this->appDir . '/webui/assets/illustrations';
    }

    public function streamDir(): string
    {
        return $this->birdsongsDir . '/StreamData';
    }

    public function authEnabled(): bool
    {
        return $this->adminPassword !== '';
    }
}
