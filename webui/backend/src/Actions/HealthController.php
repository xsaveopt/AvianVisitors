<?php

declare(strict_types=1);

namespace AvianVisitors\Actions;

use AvianVisitors\Database;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

final class HealthController
{
    public function __construct(
        private readonly Database $db,
    ) {}

    public function __invoke(Request $request, Response $response): Response
    {
        $healthy = $this->db->exists();
        $response->getBody()->write($healthy ? 'up' : 'degraded');
        return $response
            ->withHeader('Content-Type', 'text/plain; charset=utf-8')
            ->withHeader('Cache-Control', 'no-store')
            ->withStatus($healthy ? 200 : 503);
    }
}
