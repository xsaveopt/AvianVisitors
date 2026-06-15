<?php

declare(strict_types=1);

namespace AvianVisitors\Middleware;

use AvianVisitors\Config;
use Psr\Http\Message\ResponseFactoryInterface;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface as Handler;

final class AuthMiddleware implements MiddlewareInterface
{
    public function __construct(
        private readonly Config $config,
        private readonly ResponseFactoryInterface $responseFactory,
    ) {}

    public function process(Request $request, Handler $handler): Response
    {
        if (!$this->config->authEnabled() || $this->valid($request)) {
            return $handler->handle($request);
        }

        $response = $this->responseFactory->createResponse(401)->withHeader(
            'Content-Type',
            'application/json; charset=utf-8',
        );
        $response->getBody()->write((string) json_encode(['error' => 'unauthorized']));
        return $response;
    }

    private function valid(Request $request): bool
    {
        $header = $request->getHeaderLine('Authorization');
        if (stripos($header, 'basic ') !== 0) {
            return false;
        }
        $decoded = base64_decode(substr($header, 6), true);
        if ($decoded === false || !str_contains($decoded, ':')) {
            return false;
        }
        [$user, $pass] = explode(':', $decoded, 2);
        return hash_equals($this->config->adminUser, $user) && hash_equals($this->config->adminPassword, $pass);
    }
}
