<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

use AvianVisitors\Support\Json;
use PHPUnit\Framework\TestCase;
use Slim\Psr7\Response;

final class JsonTest extends TestCase
{
    public function testWriteSetsBodyStatusAndContentType(): void
    {
        $res = Json::write(new Response(), ['a' => 1, 'b' => 'x'], 201);
        $this->assertSame(201, $res->getStatusCode());
        $this->assertSame('application/json; charset=utf-8', $res->getHeaderLine('Content-Type'));
        $this->assertSame('{"a":1,"b":"x"}', (string) $res->getBody());
    }

    public function testWriteDefaultsTo200(): void
    {
        $this->assertSame(200, Json::write(new Response(), [])->getStatusCode());
    }

    public function testErrorWrapsMessage(): void
    {
        $res = Json::error(new Response(), 'bad input', 400);
        $this->assertSame(400, $res->getStatusCode());
        $this->assertSame('{"error":"bad input"}', (string) $res->getBody());
    }
}
