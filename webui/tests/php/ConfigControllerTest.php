<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

use PHPUnit\Framework\Attributes\DataProvider;

final class ConfigControllerTest extends SlimTestCase
{
    private string $original = '';

    protected static function adminPassword(): string
    {
        return '';
    }

    protected function setUp(): void
    {
        parent::setUp();
        $this->original = (string) file_get_contents($this->confPath());
    }

    protected function tearDown(): void
    {
        file_put_contents($this->confPath(), $this->original);
    }

    private function confPath(): string
    {
        return self::base() . '/app/birdnet.conf';
    }

    /** @return array{status:int,headers:array<string,string[]>,data:array<string,mixed>} */
    private function post(array $body): array
    {
        return $this->json('POST', '/api/config', [], (string) json_encode($body));
    }

    public function testGetReturnsTypedValuesAndMeta(): void
    {
        $res = $this->json('GET', '/api/config');
        $this->assertSame(200, $res['status']);
        $values = $res['data']['values'];
        $this->assertSame(0.7, $values['CONFIDENCE']);
        $this->assertSame(50, $values['MAX_FILES_SPECIES']);
        $this->assertSame(95, $values['PURGE_THRESHOLD']);
        $this->assertSame('Test Garden', $values['SITE_NAME']);
        $this->assertArrayNotHasKey('THEME', $values);
        $this->assertArrayNotHasKey('REC_CARD', $values);
        $this->assertSame('enum', $res['data']['meta']['MODEL']['type']);
        $this->assertFalse($res['data']['preserve']);
    }

    public function testValidStringIsWrittenAndQuoted(): void
    {
        $res = $this->post(['SITE_NAME' => "Owl's Garden, No. 2"]);
        $this->assertSame(200, $res['status']);
        $this->assertTrue($res['data']['ok']);
        $this->assertSame(['SITE_NAME' => "Owl's Garden, No. 2"], $res['data']['updates']);
        $this->assertSame([], $res['data']['restarted']);
        $conf = (string) file_get_contents($this->confPath());
        $this->assertStringContainsString("SITE_NAME=\"Owl's Garden, No. 2\"\n", $conf);
        $this->assertStringContainsString("CONFIDENCE=0.7\n", $conf);
        $this->assertSame("Owl's Garden, No. 2", $this->json('GET', '/api/config')['data']['values']['SITE_NAME']);
    }

    public function testUnknownKeyIsRejected(): void
    {
        $res = $this->post(['REC_CARD' => 'hw:1']);
        $this->assertSame(400, $res['status']);
        $this->assertSame('validation', $res['data']['error']);
        $this->assertSame(['REC_CARD' => 'unknown'], $res['data']['fields']);
        $this->assertSame($this->original, file_get_contents($this->confPath()));
    }

    public function testOneInvalidFieldBlocksTheWholeUpdate(): void
    {
        $res = $this->post(['SITE_NAME' => 'Fine', 'CONFIDENCE' => 5]);
        $this->assertSame(400, $res['status']);
        $this->assertSame(['CONFIDENCE' => 'out of range'], $res['data']['fields']);
        $this->assertSame($this->original, file_get_contents($this->confPath()));
    }

    public static function invalidValues(): array
    {
        return [
            'enum not listed' => ['THEME', 'blue', 'invalid value'],
            'enum case differs' => ['FULL_DISK', 'PURGE', 'invalid value'],
            'enum model not listed' => ['MODEL', 'BirdNET_GLOBAL_6K_V2.4', 'invalid value'],
            'float above max' => ['CONFIDENCE', 1.0, 'out of range'],
            'float below min' => ['SENSITIVITY', 0.49, 'out of range'],
            'latitude above max' => ['LATITUDE', 90.5, 'out of range'],
            'int below min' => ['PURGE_THRESHOLD', 49, 'out of range'],
            'int above max' => ['MAX_FILES_SPECIES', 100001, 'out of range'],
            'string too long' => ['SITE_NAME', str_repeat('a', 61), 'too long'],
            'string with semicolon' => ['SITE_NAME', 'Garden; reboot', 'invalid characters'],
            'string with double quote' => ['SITE_NAME', 'Garden"', 'invalid characters'],
            'string with dollar' => ['SITE_NAME', 'Garden $HOME', 'invalid characters'],
            'string with non ascii' => ['SITE_NAME', "Gard\u{00e9}n", 'invalid characters'],
            'string with trailing newline' => ['SITE_NAME', "Garden\n", 'invalid characters'],
            'string with embedded newline' => ['SITE_NAME', "Garden\nMODEL=x", 'invalid characters'],
            'float not numeric' => ['SF_THRESH', 'abc', null],
            'int not numeric' => ['MAX_FILES_SPECIES', 'lots', null],
        ];
    }

    #[DataProvider('invalidValues')]
    public function testInvalidValueIsRejected(string $key, mixed $value, ?string $reason): void
    {
        $res = $this->post([$key => $value]);
        $this->assertSame(400, $res['status']);
        $this->assertSame([$key], array_keys($res['data']['fields'] ?? []));
        if ($reason !== null) {
            $this->assertSame($reason, $res['data']['fields'][$key]);
        }
        $this->assertSame($this->original, file_get_contents($this->confPath()));
    }

    public static function validValues(): array
    {
        return [
            'enum model' => ['MODEL', 'Perch_v2', 'Perch_v2'],
            'enum theme' => ['THEME', 'dark', 'dark'],
            'float at max' => ['CONFIDENCE', 0.99, 0.99],
            'float at min' => ['SF_THRESH', 0, 0.0],
            'float from numeric string' => ['OVERLAP', '1.5', 1.5],
            'negative longitude' => ['LONGITUDE', -180, -180.0],
            'int at min' => ['PURGE_THRESHOLD', 50, 50],
            'int from numeric string' => ['MAX_FILES_SPECIES', '200', 200],
            'string at maxlen' => ['SITE_NAME', str_repeat('a', 60), str_repeat('a', 60)],
            'empty string' => ['SITE_NAME', '', ''],
        ];
    }

    #[DataProvider('validValues')]
    public function testValidValueIsAccepted(string $key, mixed $value, mixed $stored): void
    {
        $res = $this->post([$key => $value]);
        $this->assertSame(200, $res['status']);
        $this->assertEquals([$key => $stored], $res['data']['updates']);
    }

    public function testPreserveTrueKeepsEveryRecording(): void
    {
        $res = $this->post(['preserve' => true]);
        $this->assertSame(200, $res['status']);
        $this->assertSame(['MAX_FILES_SPECIES' => 99999], $res['data']['updates']);
        $this->assertStringContainsString("MAX_FILES_SPECIES=99999\n", (string) file_get_contents($this->confPath()));
        $this->assertTrue($this->json('GET', '/api/config')['data']['preserve']);
    }

    public function testPreserveFalseRestoresTheDefaultCap(): void
    {
        $this->post(['preserve' => true]);
        $res = $this->post(['preserve' => false]);
        $this->assertSame(['MAX_FILES_SPECIES' => 50], $res['data']['updates']);
        $this->assertFalse($this->json('GET', '/api/config')['data']['preserve']);
    }

    public function testPreserveIsNotReportedAsUnknown(): void
    {
        $res = $this->post(['preserve' => true, 'THEME' => 'dark']);
        $this->assertSame(200, $res['status']);
        $this->assertSame(['THEME' => 'dark', 'MAX_FILES_SPECIES' => 99999], $res['data']['updates']);
    }

    public function testModelSettingsTriggerRestart(): void
    {
        $res = $this->post(['CONFIDENCE' => 0.5]);
        $this->assertSame(200, $res['status']);
        $this->assertSame(['analysis', 'recording'], array_keys($res['data']['restarted']));
        foreach ($res['data']['restarted'] as $ok) {
            $this->assertIsBool($ok);
        }
    }

    public function testDisplaySettingsDoNotRestart(): void
    {
        $res = $this->post(['THEME' => 'dark', 'SITE_NAME' => 'Garden', 'PURGE_THRESHOLD' => 90]);
        $this->assertSame(200, $res['status']);
        $this->assertSame([], $res['data']['restarted']);
    }

    public function testMalformedJsonIsRejected(): void
    {
        $res = $this->json('POST', '/api/config', [], '{');
        $this->assertSame(400, $res['status']);
    }

    public function testScalarJsonBodyIsRejected(): void
    {
        $res = $this->request('POST', '/api/config', [], '"SITE_NAME"');
        $this->assertSame(400, $res['status']);
    }

    public function testThemeFallsBackToLight(): void
    {
        $this->assertSame('light', $this->json('GET', '/api/theme')['data']['theme']);
        $this->post(['THEME' => 'dark']);
        $this->assertSame('dark', $this->json('GET', '/api/theme')['data']['theme']);
    }
}
