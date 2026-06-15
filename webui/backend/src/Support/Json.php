<?php

declare(strict_types=1);

namespace AvianVisitors\Support;

use Psr\Http\Message\ResponseInterface as Response;

final class Json
{
    public static function write(Response $response, mixed $data, int $status = 200): Response
    {
        $response->getBody()->write((string) json_encode($data));
        return $response->withHeader('Content-Type', 'application/json; charset=utf-8')->withStatus($status);
    }

    public static function error(Response $response, string $message, int $status): Response
    {
        return self::write($response, ['error' => $message], $status);
    }
}
