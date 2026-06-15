<?php

declare(strict_types=1);

namespace AvianVisitors\Actions;

use AvianVisitors\Support\Json;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

final class MenuController
{
    public function __invoke(Request $request, Response $response): Response
    {
        return Json::write($response->withHeader('Cache-Control', 'no-store'), [
            'items' => [
                ['label' => 'settings', 'href' => '/#admin=settings', 'native' => true],
                ['label' => 'system', 'href' => '/#admin=system', 'native' => true],
                ['label' => 'logs', 'href' => '/#admin=logs', 'native' => true],
                ['label' => 'tools', 'href' => '/#admin=tools', 'native' => true],
            ],
        ]);
    }
}
