<?php

declare(strict_types=1);

namespace AvianVisitors\Tests\Support;

use DateTimeImmutable;
use SQLite3;

final class Runtime
{
    public const SPECIES = [
        ['sci' => 'Calypte anna', 'com' => "Anna's Hummingbird", 'dir' => 'Annas_Hummingbird'],
        ['sci' => 'Passer domesticus', 'com' => 'House Sparrow', 'dir' => 'House_Sparrow'],
        ['sci' => 'Turdus migratorius', 'com' => 'American Robin', 'dir' => 'American_Robin'],
        ['sci' => 'Corvus brachyrhynchos', 'com' => 'American Crow', 'dir' => 'American_Crow'],
    ];

    public static function build(string $base): string
    {
        $webui = dirname(__DIR__, 2);
        $docroot = $base . '/app';

        self::rmrf($base);
        @mkdir($docroot . '/webui/assets/illustrations', 0o777, true);
        @mkdir($docroot . '/birdnet', 0o777, true);
        @mkdir($base . '/BirdSongs/Extracted/By_Date', 0o777, true);
        @mkdir($base . '/BirdNET-Pi/birdnet/model', 0o777, true);

        $bundled = glob($webui . '/assets/illustrations/*.avif');
        sort($bundled);
        foreach ($bundled as $illustration) {
            if (filesize($illustration) > 1024) {
                copy($illustration, $docroot . '/webui/assets/illustrations/' . basename($illustration));
                break;
            }
        }

        @mkdir($docroot . '/birdnet/model', 0o777, true);
        self::writeConf($docroot . '/birdnet.conf');
        self::writeBirdsJson($base . '/BirdNET-Pi/birdnet/birds.json');
        self::writeLabels($base . '/BirdNET-Pi/birdnet/model/labels.txt');
        self::writeBirdsJson($docroot . '/birdnet/birds.json');
        self::writeLabels($docroot . '/birdnet/model/labels.txt');
        $rows = self::detectionRows();
        self::buildDb($docroot . '/birdnet/birds.db', $rows);
        self::writeMedia($base . '/BirdSongs/Extracted/By_Date', $rows);

        return $docroot;
    }

    public static function detectionRows(): array
    {
        $now = new DateTimeImmutable('now');
        $today = $now->format('Y-m-d');
        $threeAgo = $now->modify('-3 days')->format('Y-m-d');
        $fortyAgo = $now->modify('-40 days')->format('Y-m-d');
        $t = $now->format('H:i:s');

        return [
            ['Calypte anna', "Anna's Hummingbird", 0.95, $today, $t, 'Annas_Hummingbird-95-' . $today . '.mp3'],
            ['Calypte anna', "Anna's Hummingbird", 0.90, $today, $t, 'Annas_Hummingbird-90-' . $today . '.mp3'],
            ['Calypte anna', "Anna's Hummingbird", 0.85, $today, '00:00:30', 'Annas_Hummingbird-85-' . $today . '.mp3'],
            ['Passer domesticus', 'House Sparrow', 0.72, $today, $t, 'House_Sparrow-72-' . $today . '.mp3'],
            [
                'Turdus migratorius',
                'American Robin',
                0.66,
                $threeAgo,
                '08:15:00',
                'American_Robin-66-' . $threeAgo . '.mp3',
            ],
            [
                'Turdus migratorius',
                'American Robin',
                0.61,
                $threeAgo,
                '09:20:00',
                'American_Robin-61-' . $threeAgo . '.mp3',
            ],
            [
                'Corvus brachyrhynchos',
                'American Crow',
                0.80,
                $fortyAgo,
                '07:00:00',
                'American_Crow-80-' . $fortyAgo . '.mp3',
            ],
        ];
    }

    private static function buildDb(string $path, array $rows): void
    {
        @unlink($path);
        $db = new SQLite3($path);
        $db->exec(
            'CREATE TABLE detections ('
            . 'Date DATE, Time TIME, Sci_Name VARCHAR(100) NOT NULL, Com_Name VARCHAR(100) NOT NULL, '
            . 'Confidence FLOAT, Lat FLOAT, Lon FLOAT, Cutoff FLOAT, Week INT, Sens FLOAT, Overlap FLOAT, '
            . 'File_Name VARCHAR(100) NOT NULL)',
        );
        $stmt = $db->prepare(
            'INSERT INTO detections (Date, Time, Sci_Name, Com_Name, Confidence, Lat, Lon, Cutoff, Week, Sens, Overlap, File_Name) '
            . 'VALUES (:d, :t, :sci, :com, :conf, 0, 0, 0, 0, 0, 0, :file)',
        );
        foreach ($rows as $r) {
            $stmt->bindValue(':d', $r[3]);
            $stmt->bindValue(':t', $r[4]);
            $stmt->bindValue(':sci', $r[0]);
            $stmt->bindValue(':com', $r[1]);
            $stmt->bindValue(':conf', $r[2]);
            $stmt->bindValue(':file', $r[5]);
            $stmt->execute();
            $stmt->reset();
        }
        $db->close();
    }

    private static function writeMedia(string $byDate, array $rows): void
    {
        $mp3 = str_repeat("\x00", 256);
        $png =
            base64_decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9' . 'awAAAABJRU5ErkJggg==',
                true,
            ) . str_repeat("\x00", 64);
        foreach ($rows as $r) {
            $dir = $byDate . '/' . $r[3] . '/' . self::dirFor($r[1]);
            @mkdir($dir, 0o777, true);
            file_put_contents($dir . '/' . $r[5], $mp3);
            file_put_contents($dir . '/' . substr($r[5], 0, -4) . '.png', $png);
        }
    }

    private static function dirFor(string $com): string
    {
        foreach (self::SPECIES as $s) {
            if ($s['com'] === $com) {
                return $s['dir'];
            }
        }
        return str_replace(' ', '_', $com);
    }

    private static function writeConf(string $path): void
    {
        $lines = [
            'SITE_NAME=Test Garden',
            'CONFIDENCE=0.7',
            'SENSITIVITY=1.25',
            'SF_THRESH=0.03',
            'OVERLAP=0.0',
            'MAX_FILES_SPECIES=50',
            'FULL_DISK=purge',
            'PURGE_THRESHOLD=95',
            'LATITUDE=52.37',
            'LONGITUDE=4.90',
            'REC_CARD=default',
            'MODEL=BirdNET_GLOBAL_6K_V2.4',
            'RTSP_STREAM=',
        ];
        file_put_contents($path, implode("\n", $lines) . "\n");
    }

    private static function writeBirdsJson(string $path): void
    {
        $rows = array_map(static fn($s) => ['sci' => $s['sci'], 'com' => $s['com']], self::SPECIES);
        file_put_contents($path, json_encode($rows));
    }

    private static function writeLabels(string $path): void
    {
        $lines = array_map(static fn($s) => $s['sci'] . '_' . $s['com'], self::SPECIES);
        file_put_contents($path, implode("\n", $lines) . "\n");
    }

    public static function rmrf(string $path): void
    {
        if (!file_exists($path)) {
            return;
        }
        if (is_file($path) || is_link($path)) {
            @unlink($path);
            return;
        }
        foreach (scandir($path) as $entry) {
            if ($entry === '.' || $entry === '..') {
                continue;
            }
            self::rmrf($path . '/' . $entry);
        }
        @rmdir($path);
    }
}
