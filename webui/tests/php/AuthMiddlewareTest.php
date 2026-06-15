<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

use AvianVisitors\Config;
use AvianVisitors\Middleware\AuthMiddleware;
use PHPUnit\Framework\TestCase;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Psr\Http\Server\RequestHandlerInterface as Handler;
use Slim\Psr7\Factory\ResponseFactory;
use Slim\Psr7\Factory\ServerRequestFactory;

final class AuthMiddlewareTest extends TestCase
{
    private const USER = 'admin';
    private const PASS = 's3cret-pw';

    private function handler(): Handler
    {
        return new class implements Handler {
            public function handle(Request $request): Response
            {
                return (new ResponseFactory())->createResponse(200);
            }
        };
    }

    private function middleware(#[\SensitiveParameter] string $password): AuthMiddleware
    {
        $config = new Config('/app', '/songs', '/logs', self::USER, $password, 'ua');
        return new AuthMiddleware($config, new ResponseFactory());
    }

    private function dispatch(#[\SensitiveParameter] string $password, array $headers): int
    {
        $request = (new ServerRequestFactory())->createServerRequest('GET', '/api/menu');
        foreach ($headers as $k => $v) {
            $request = $request->withHeader($k, $v);
        }
        return $this->middleware($password)->process($request, $this->handler())->getStatusCode();
    }

    private function basic(string $user, string $pass): array
    {
        return ['Authorization' => 'Basic ' . base64_encode("{$user}:{$pass}")];
    }

    public function testDisabledAuthPassesThrough(): void
    {
        $this->assertSame(200, $this->dispatch('', []));
    }

    public function testMissingHeaderRejected(): void
    {
        $this->assertSame(401, $this->dispatch(self::PASS, []));
    }

    public function testWrongSchemeRejected(): void
    {
        $this->assertSame(401, $this->dispatch(self::PASS, [
            'Authorization' => 'Bearer ' . base64_encode('admin:s3cret-pw'),
        ]));
    }

    public function testMalformedBase64Rejected(): void
    {
        $this->assertSame(401, $this->dispatch(self::PASS, ['Authorization' => 'Basic !!!not-base64!!!']));
    }

    public function testMissingColonRejected(): void
    {
        $this->assertSame(401, $this->dispatch(self::PASS, ['Authorization' => 'Basic ' . base64_encode('nocolon')]));
    }

    public function testWrongPasswordRejected(): void
    {
        $this->assertSame(401, $this->dispatch(self::PASS, $this->basic(self::USER, 'nope')));
    }

    public function testCorrectCredentialsAccepted(): void
    {
        $this->assertSame(200, $this->dispatch(self::PASS, $this->basic(self::USER, self::PASS)));
    }
}
