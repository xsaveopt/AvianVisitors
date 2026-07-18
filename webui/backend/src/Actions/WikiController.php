<?php

declare(strict_types=1);

namespace AvianVisitors\Actions;

use AvianVisitors\Config;
use AvianVisitors\Support\Json;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

final class WikiController
{
    public function __construct(
        private readonly Config $config,
    ) {}

    public function __invoke(Request $request, Response $response): Response
    {
        $sci = trim((string) ($request->getQueryParams()['sci'] ?? ''));
        if ($sci === '') {
            return Json::error($response, 'sci required', 400);
        }
        if (!preg_match('/^[A-Za-z]{2,40}(?:[ ][a-z]{2,40}){1,3}$/', $sci)) {
            return Json::error($response, 'invalid sci', 400);
        }

        $ctx = stream_context_create([
            'http' => ['header' => "User-Agent: {$this->config->userAgent}\r\n", 'timeout' => 8],
        ]);
        $url = 'https://en.wikipedia.org/api/rest_v1/page/summary/' . rawurlencode($sci);
        $raw = @file_get_contents($url, false, $ctx);
        if ($raw === false) {
            return Json::write($response, ['extract' => null, 'thumbnail' => null]);
        }
        /** @var array{extract?: string, title?: string, thumbnail?: array{source?: string}}|scalar|null $j */
        $j = json_decode($raw, true);
        if (!is_array($j)) {
            return Json::write($response, ['extract' => null, 'thumbnail' => null]);
        }

        $thumb = $j['thumbnail']['source'] ?? null;
        if ($thumb) {
            $host = parse_url($thumb, PHP_URL_HOST) ?: '';
            if (!preg_match('/(?:^|\.)(?:wikimedia\.org|wikipedia\.org)$/i', $host)) {
                $thumb = null;
            }
        }

        return Json::write($response, [
            'extract' => $j['extract'] ?? null,
            'thumbnail' => $thumb ? ['source' => $thumb] : null,
            'title' => $j['title'] ?? null,
        ]);
    }
}
