<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

use AvianVisitors\Config;
use AvianVisitors\Kernel;
use AvianVisitors\Tests\Support\Runtime;
use PHPUnit\Framework\TestCase;
use Slim\App;
use Slim\Psr7\Factory\ServerRequestFactory;

abstract class SlimTestCase extends TestCase
{
    private static ?string $base = null;
    private static ?string $docroot = null;
    protected App $app;
    protected ServerRequestFactory $requests;

    abstract protected static function adminPassword(): string;

    public static function setUpBeforeClass(): void
    {
        self::$base = sys_get_temp_dir() . '/av-slim-' . getmypid() . '-' . uniqid();
        self::$docroot = Runtime::build(self::$base);
    }

    public static function tearDownAfterClass(): void
    {
        if (self::$base !== null) {
            Runtime::rmrf(self::$base);
            self::$base = null;
            self::$docroot = null;
        }
    }

    protected function setUp(): void
    {
        putenv('AV_APP_DIR=' . self::$docroot);
        putenv('AV_BIRDSONGS_DIR=' . self::$base . '/BirdSongs');
        putenv('AV_LOGS_DIR=' . self::$base . '/logs');
        putenv('AV_ADMIN_USER=admin');
        putenv('AV_ADMIN_PASSWORD=' . static::adminPassword());
        $this->app = Kernel::create(Config::fromEnv());
        $this->requests = new ServerRequestFactory();
    }

    /**
     * @param array<string,string> $headers
     * @return array{status:int,headers:array<string,string[]>,body:string}
     */
    protected function request(string $method, string $path, array $headers = [], ?string $body = null): array
    {
        $request = $this->requests->createServerRequest($method, $path);
        $query = parse_url($path, PHP_URL_QUERY);
        if (is_string($query)) {
            parse_str($query, $params);
            $request = $request->withQueryParams($params);
        }
        foreach ($headers as $k => $v) {
            $request = $request->withHeader($k, $v);
        }
        if ($body !== null) {
            $request->getBody()->write($body);
            $request->getBody()->rewind();
            $request = $request->withHeader('Content-Type', 'application/json');
        }
        $response = $this->app->handle($request);
        return [
            'status' => $response->getStatusCode(),
            'headers' => $response->getHeaders(),
            'body' => (string) $response->getBody(),
        ];
    }

    /** @return array{status:int,headers:array<string,string[]>,data:array<string,mixed>} */
    protected function json(string $method, string $path, array $headers = [], ?string $body = null): array
    {
        $res = $this->request($method, $path, $headers, $body);
        $decoded = json_decode($res['body'], true);
        $this->assertIsArray($decoded, "non-json from {$path}: " . substr($res['body'], 0, 200));
        return ['status' => $res['status'], 'headers' => $res['headers'], 'data' => $decoded];
    }

    protected static function basic(string $user, string $pass): array
    {
        return ['Authorization' => 'Basic ' . base64_encode("{$user}:{$pass}")];
    }
}
