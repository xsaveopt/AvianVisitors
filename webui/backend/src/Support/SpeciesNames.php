<?php

declare(strict_types=1);

namespace AvianVisitors\Support;

use AvianVisitors\Config;

final class SpeciesNames
{
    public function __construct(
        private readonly Config $config,
    ) {}

    public function commonFor(string $sci): ?string
    {
        $birds = $this->config->birdsJsonPath();
        if (is_readable($birds)) {
            $list = json_decode((string) file_get_contents($birds), true);
            if (is_array($list)) {
                foreach ($list as $row) {
                    if (!is_array($row)) {
                        continue;
                    }
                    $rowSci = $row['sci'] ?? $row['scientific'] ?? $row['scientificName'] ?? '';
                    $rowCom = $row['com'] ?? $row['common'] ?? $row['commonName'] ?? '';
                    if (strcasecmp(trim((string) $rowSci), $sci) === 0 && $rowCom) {
                        return str_replace(' ', '_', (string) $rowCom);
                    }
                }
            }
        }

        $labels = $this->config->labelsPath();
        if (is_readable($labels)) {
            foreach (file($labels, FILE_IGNORE_NEW_LINES) as $line) {
                if (!str_contains($line, '_')) {
                    continue;
                }
                [$s, $c] = explode('_', $line, 2);
                if (strcasecmp(trim($s), $sci) === 0) {
                    return str_replace(' ', '_', trim($c));
                }
            }
        }

        return null;
    }
}
