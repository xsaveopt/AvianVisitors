<?php

declare(strict_types=1);

namespace AvianVisitors\Actions;

use AvianVisitors\Config;
use AvianVisitors\Support\Json;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\Psr7\Factory\StreamFactory;

final class IllustrationController
{
    public function __construct(
        private readonly Config $config,
    ) {}

    public function __invoke(Request $request, Response $response): Response
    {
        $params = $request->getQueryParams();
        $sci = trim((string) ($params['sci'] ?? ''));
        if ($sci === '') {
            return Json::error($response, 'sci required', 400);
        }
        if (!preg_match('/^[A-Za-z]{2,40}(?:[ ][a-z]{2,40}){1,3}$/', $sci)) {
            return Json::error($response, 'invalid sci', 400);
        }

        $slug = trim((string) preg_replace('/[^a-z0-9]+/', '-', strtolower($sci)), '-');
        $pose = (int) ($params['pose'] ?? 1);
        if ($pose < 1 || $pose > 99) {
            $pose = 1;
        }
        $suffix = $pose === 1 ? '' : "-{$pose}";

        $dir = $this->config->illustrationsDir();
        $candidates = ["{$dir}/{$slug}{$suffix}.avif"];
        if ($pose !== 1) {
            $candidates[] = "{$dir}/{$slug}.avif";
        }

        foreach ($candidates as $path) {
            if (is_file($path) && filesize($path) > 1024) {
                return $this->serveImage($response, $path);
            }
        }

        return $this->placeholder($response, $sci, (string) ($params['com'] ?? ''));
    }

    private function serveImage(Response $response, string $path): Response
    {
        $stream = (new StreamFactory())->createStreamFromFile($path);
        return $response
            ->withHeader('Content-Type', 'image/avif')
            ->withHeader('Cache-Control', 'public, max-age=86400')
            ->withHeader('Content-Length', (string) filesize($path))
            ->withBody($stream);
    }

    private function placeholder(Response $response, string $sci, string $com): Response
    {
        $label = htmlspecialchars($com !== '' ? $com : $sci, ENT_QUOTES);
        $svg = <<<SVG
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="320" height="320" role="img" aria-label="{$label}: illustration not generated">
              <rect x="10" y="10" width="300" height="300" rx="26" fill="#efe7d8" stroke="#d8ccb4" stroke-width="2"/>
              <text x="160" y="150" text-anchor="middle" font-family="ui-sans-serif,system-ui,sans-serif" font-size="56" fill="#cdbfa3">?</text>
              <text x="160" y="210" text-anchor="middle" font-family="ui-sans-serif,system-ui,sans-serif" font-size="19" font-style="italic" fill="#6b5e44">{$label}</text>
              <text x="160" y="244" text-anchor="middle" font-family="ui-monospace,monospace" font-size="12" fill="#9a8c6e">illustration not generated</text>
            </svg>
            SVG;
        $response->getBody()->write($svg);
        return $response
            ->withHeader('Content-Type', 'image/svg+xml; charset=utf-8')
            ->withHeader('Cache-Control', 'public, max-age=3600')
            ->withHeader('X-Cutout-Status', 'not-generated');
    }
}
