<?php

declare(strict_types=1);

namespace AvianVisitors\Support;

use AvianVisitors\Config;

final class MediaLocator
{
    private const MIN_SIZE = 64;

    public function __construct(
        private readonly Config $config,
        private readonly SpeciesNames $names,
    ) {}

    public function validSci(string $sci): bool
    {
        return (bool) preg_match('/^[A-Za-z]{2,40}(?:[ ][a-z]{2,40}){1,3}$/', $sci);
    }

    public function validFileName(string $file, string $ext): bool
    {
        if (str_contains($file, '..')) {
            return false;
        }
        if ($ext === 'mp3') {
            return (bool) preg_match("/^[\\p{L}\\p{N}_.:'-]+\\.mp3$/u", $file);
        }
        return (bool) preg_match("/^[\\p{L}\\p{N}_.:'-]+\\.(mp3|png)$/u", $file);
    }

    public function findByFile(string $file, string $ext): ?string
    {
        $target = $file;
        if ($ext === 'png' && !str_ends_with($target, '.png')) {
            $target .= '.png';
        }

        $byDate = $this->config->byDateDir();
        $date = null;
        $m = [];
        if (preg_match('/(\d{4}-\d{2}-\d{2})/', $target, $m)) {
            $date = $m[1];
        }

        if ($date !== null) {
            $dayDir = "{$byDate}/{$date}";
            $hit = $this->scanDay($dayDir, $target);
            if ($hit !== null) {
                return $hit;
            }
        }

        if (is_dir($byDate)) {
            foreach (scandir($byDate) ?: [] as $d) {
                if ($d[0] === '.') {
                    continue;
                }
                $hit = $this->scanDay("{$byDate}/{$d}", $target);
                if ($hit !== null) {
                    return $hit;
                }
            }
        }

        return null;
    }

    public function findNewestBySci(string $sci, string $ext): ?string
    {
        $common = $this->names->commonFor($sci) ?? str_replace(' ', '_', $sci);
        $root = $this->config->byDateDir();
        if (!is_dir($root)) {
            return null;
        }

        $want = $this->normalize($common);
        $dates = scandir($root, SCANDIR_SORT_DESCENDING) ?: [];
        foreach ($dates as $date) {
            if ($date[0] === '.') {
                continue;
            }
            $dayDir = "{$root}/{$date}";
            if (!is_dir($dayDir)) {
                continue;
            }
            $speciesDir = $this->matchSpeciesDir($dayDir, $want);
            if ($speciesDir === null) {
                continue;
            }
            $files = scandir($speciesDir, SCANDIR_SORT_DESCENDING) ?: [];
            foreach ($files as $f) {
                if (str_ends_with($f, ".{$ext}") && $this->bigEnough("{$speciesDir}/{$f}")) {
                    return "{$speciesDir}/{$f}";
                }
            }
        }

        return null;
    }

    private function scanDay(string $dayDir, string $target): ?string
    {
        if (!is_dir($dayDir)) {
            return null;
        }
        foreach (scandir($dayDir) ?: [] as $sub) {
            if ($sub[0] === '.') {
                continue;
            }
            $path = "{$dayDir}/{$sub}/{$target}";
            if (is_file($path) && $this->bigEnough($path)) {
                return $path;
            }
        }
        return null;
    }

    private function matchSpeciesDir(string $dayDir, string $want): ?string
    {
        foreach (scandir($dayDir) ?: [] as $sub) {
            if ($sub[0] === '.' || !is_dir("{$dayDir}/{$sub}")) {
                continue;
            }
            if ($this->normalize($sub) === $want) {
                return "{$dayDir}/{$sub}";
            }
        }
        return null;
    }

    private function normalize(string $s): string
    {
        return preg_replace('/[^a-z0-9]/', '', strtolower($s)) ?? '';
    }

    private function bigEnough(string $path): bool
    {
        return (int) @filesize($path) >= self::MIN_SIZE;
    }
}
