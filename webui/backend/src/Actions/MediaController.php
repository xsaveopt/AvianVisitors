<?php

declare(strict_types=1);

namespace AvianVisitors\Actions;

use AvianVisitors\Support\MediaLocator;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\Psr7\Factory\StreamFactory;

final class MediaController
{
    public function __construct(
        private readonly MediaLocator $locator,
    ) {}

    public function recording(Request $request, Response $response): Response
    {
        return $this->serveMedia($request, $response, 'mp3', 'audio/mpeg', true);
    }

    public function spectrogram(Request $request, Response $response): Response
    {
        return $this->serveMedia($request, $response, 'png', 'image/png', false);
    }

    private function serveMedia(
        Request $request,
        Response $response,
        string $ext,
        string $contentType,
        bool $acceptRanges,
    ): Response {
        $params = $request->getQueryParams();
        $sci = trim((string) ($params['sci'] ?? ''));
        $file = trim((string) ($params['file'] ?? ''));

        if ($sci === '' && $file === '') {
            return $this->text($response, 'sci or file required', 400);
        }
        if ($sci !== '' && !$this->locator->validSci($sci)) {
            return $this->text($response, 'invalid sci', 400);
        }

        if ($file !== '') {
            if (!$this->locator->validFileName($file, $ext)) {
                return $this->text($response, 'invalid file name', 400);
            }
            $path = $this->locator->findByFile($file, $ext);
            if ($path === null) {
                return $this->text($response, 'not found', 404);
            }
            return $this->serve($response, $path, $contentType, $acceptRanges, 86400);
        }

        $path = $this->locator->findNewestBySci($sci, $ext);
        if ($path === null) {
            return $this->text($response, 'no media for ' . htmlspecialchars($sci), 404);
        }
        return $this->serve($response, $path, $contentType, $acceptRanges, 60);
    }

    private function serve(
        Response $response,
        string $path,
        string $contentType,
        bool $acceptRanges,
        int $maxAge,
    ): Response {
        $stream = new StreamFactory()->createStreamFromFile($path);
        $response = $response
            ->withHeader('Content-Type', $contentType)
            ->withHeader('Content-Length', (string) filesize($path))
            ->withHeader('Cache-Control', "public, max-age={$maxAge}")
            ->withBody($stream);
        if ($acceptRanges) {
            $response = $response->withHeader('Accept-Ranges', 'bytes');
        }
        return $response;
    }

    private function text(Response $response, string $message, int $status): Response
    {
        $response->getBody()->write($message);
        return $response->withHeader('Content-Type', 'text/plain; charset=utf-8')->withStatus($status);
    }
}
