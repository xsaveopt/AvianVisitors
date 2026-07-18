<?php

declare(strict_types=1);

namespace AvianVisitors\Actions;

use AvianVisitors\Support\Conf;
use AvianVisitors\Support\Json;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

final class ConfigController
{
    private const ALLOWED = [
        'MODEL' => [
            'type' => 'enum',
            'values' => [
                'BirdNET_GLOBAL_6K_V2.4_Model_FP16',
                'BirdNET_6K_GLOBAL_MODEL',
                'BirdNET-Go_classifier_20250916',
                'Perch_v2',
            ],
            'restart' => true,
        ],
        'CONFIDENCE' => ['type' => 'float', 'min' => 0.05, 'max' => 0.99, 'restart' => true],
        'SENSITIVITY' => ['type' => 'float', 'min' => 0.5, 'max' => 1.5, 'restart' => true],
        'SF_THRESH' => ['type' => 'float', 'min' => 0.0, 'max' => 1.0, 'restart' => true],
        'OVERLAP' => ['type' => 'float', 'min' => 0.0, 'max' => 2.5, 'restart' => true],
        'MAX_FILES_SPECIES' => ['type' => 'int', 'min' => 0, 'max' => 100000],
        'FULL_DISK' => ['type' => 'enum', 'values' => ['purge', 'keep']],
        'PURGE_THRESHOLD' => ['type' => 'int', 'min' => 50, 'max' => 99],
        'LATITUDE' => ['type' => 'float', 'min' => -90, 'max' => 90, 'restart' => true],
        'LONGITUDE' => ['type' => 'float', 'min' => -180, 'max' => 180, 'restart' => true],
        'SITE_NAME' => ['type' => 'string', 'maxlen' => 60],
        'THEME' => ['type' => 'enum', 'values' => ['light', 'dark']],
    ];

    private const SUPERVISORCTL = '/usr/bin/supervisorctl -c /etc/supervisor/supervisord.conf';

    public function __construct(
        private readonly Conf $conf,
    ) {}

    public function theme(Request $request, Response $response): Response
    {
        $conf = $this->conf->read();
        $theme = ($conf['THEME'] ?? 'light') === 'dark' ? 'dark' : 'light';
        return Json::write($response, ['theme' => $theme]);
    }

    public function get(Request $request, Response $response): Response
    {
        $conf = $this->conf->read();
        $out = [];
        foreach (self::ALLOWED as $k => $spec) {
            if (!array_key_exists($k, $conf)) {
                continue;
            }
            $v = $conf[$k];
            if ($spec['type'] === 'float') {
                $v = is_numeric($v) ? (float) $v : 0.0;
            } elseif ($spec['type'] === 'int') {
                $v = (int) $v;
            }
            $out[$k] = $v;
        }
        return Json::write($response, [
            'values' => $out,
            'meta' => self::ALLOWED,
            'preserve' => (int) ($conf['MAX_FILES_SPECIES'] ?? 0) >= 10000,
        ]);
    }

    public function post(Request $request, Response $response): Response
    {
        /** @var array<string, scalar|null>|object|null $body */
        $body = $request->getParsedBody();
        if (!is_array($body)) {
            return Json::error($response, 'bad json', 400);
        }

        $updates = [];
        $errors = [];
        foreach ($body as $k => $v) {
            if ($k === 'preserve') {
                continue;
            }
            if (!isset(self::ALLOWED[$k])) {
                $errors[$k] = 'unknown';
                continue;
            }
            $spec = self::ALLOWED[$k];
            if ($spec['type'] === 'float') {
                $v = is_numeric($v) ? (float) $v : 0.0;
                if ($v < ($spec['min'] ?? -INF) || $v > ($spec['max'] ?? INF)) {
                    $errors[$k] = 'out of range';
                    continue;
                }
            } elseif ($spec['type'] === 'int') {
                $v = is_numeric($v) ? (int) $v : 0;
                if ($v < ($spec['min'] ?? -PHP_INT_MAX) || $v > ($spec['max'] ?? PHP_INT_MAX)) {
                    $errors[$k] = 'out of range';
                    continue;
                }
            } elseif ($spec['type'] === 'enum') {
                if (!in_array($v, $spec['values'], true)) {
                    $errors[$k] = 'invalid value';
                    continue;
                }
            } else {
                $v = (string) $v;
                if (strlen($v) > ($spec['maxlen'] ?? 200)) {
                    $errors[$k] = 'too long';
                    continue;
                }
                if (!preg_match("/^[A-Za-z0-9 _.,'-]*$/u", $v)) {
                    $errors[$k] = 'invalid characters';
                    continue;
                }
            }
            $updates[$k] = $v;
        }

        if ($errors) {
            return Json::write($response, ['error' => 'validation', 'fields' => $errors], 400);
        }

        if (isset($body['preserve'])) {
            $updates['MAX_FILES_SPECIES'] = $body['preserve'] ? 99999 : 50;
        }

        if (!$this->conf->write($updates)) {
            return Json::error($response, 'write failed (check perms on birdnet.conf)', 500);
        }

        $restarted = [];
        if ($this->needsRestart($updates)) {
            foreach (['analysis', 'recording'] as $svc) {
                $rc = 0;
                $out = [];
                exec(self::SUPERVISORCTL . ' restart ' . escapeshellarg($svc) . ' 2>&1', $out, $rc);
                $restarted[$svc] = $rc === 0;
            }
        }

        return Json::write($response, ['ok' => true, 'updates' => $updates, 'restarted' => $restarted]);
    }

    private function needsRestart(array $updates): bool
    {
        foreach (array_keys($updates) as $k) {
            if (!empty(self::ALLOWED[$k]['restart'])) {
                return true;
            }
        }
        return false;
    }
}
