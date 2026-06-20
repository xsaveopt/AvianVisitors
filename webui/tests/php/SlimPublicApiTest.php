<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

use DateTimeImmutable;

final class SlimPublicApiTest extends SlimTestCase
{
    protected static function adminPassword(): string
    {
        return '';
    }

    private function today(): string
    {
        return (new DateTimeImmutable('now'))->format('Y-m-d');
    }

    public function testStatsContract(): void
    {
        $res = $this->json('GET', '/api/stats');
        $this->assertSame(200, $res['status']);
        $d = $res['data'];
        $this->assertSame(7, $d['totals']['detections']);
        $this->assertSame(4, $d['totals']['species']);
        $this->assertSame(4, $d['today']['detections']);
        $this->assertSame(2, $d['today']['species']);
        $this->assertSame(6, $d['week']['detections']);
        $this->assertSame(3, $d['week']['species']);
        $this->assertIsInt($d['last_hour']['detections']);
        $this->assertArrayHasKey('as_of', $d);
    }

    public function testLifelistOrderedByFirstSeen(): void
    {
        $res = $this->json('GET', '/api/lifelist');
        $species = $res['data']['species'];
        $this->assertCount(4, $species);
        $this->assertSame('Corvus brachyrhynchos', $species[0]['sci']);
        foreach (['sci', 'com', 'first_seen', 'last_seen', 'n', 'best_conf'] as $key) {
            $this->assertArrayHasKey($key, $species[0]);
        }
    }

    public function testRecentWindowFiltersByHours(): void
    {
        $day = $this->json('GET', '/api/recent?hours=24');
        $week = $this->json('GET', '/api/recent?hours=168');
        $this->assertCount(2, $day['data']['species']);
        $this->assertCount(3, $week['data']['species']);
        $this->assertNotNull($day['data']['species'][0]['top_file']);
    }

    public function testSpeciesDetail(): void
    {
        $res = $this->json('GET', '/api/species?sci=' . rawurlencode('Calypte anna'));
        $this->assertSame(200, $res['status']);
        $this->assertSame(3, (int) $res['data']['summary']['total']);
        $this->assertSame("Anna's Hummingbird", $res['data']['summary']['com']);
        $this->assertCount(3, $res['data']['detections']);
        $this->assertNotEmpty($res['data']['detections'][0]['file']);
    }

    public function testSpeciesRequiresSci(): void
    {
        $this->assertSame(400, $this->request('GET', '/api/species')['status']);
    }

    public function testTimeseriesAndFirstseen(): void
    {
        $ts = $this->json('GET', '/api/timeseries?days=30');
        $this->assertCount(2, $ts['data']['daily']);
        $this->assertIsArray($ts['data']['by_hour']);

        $fs = $this->json('GET', '/api/firstseen?limit=10');
        $this->assertCount(4, $fs['data']['species']);
        $this->assertSame('Corvus brachyrhynchos', end($fs['data']['species'])['sci']);
    }

    public function testWikiRejectsInvalidSci(): void
    {
        $this->assertSame(400, $this->request('GET', '/api/wiki')['status']);
        $this->assertSame(400, $this->request('GET', '/api/wiki?sci=x')['status']);
    }

    public function testCutoutServesBundledIllustration(): void
    {
        $files = glob(getenv('AV_APP_DIR') . '/webui/assets/illustrations/*.avif');
        if ($files === [] || $files === false) {
            $this->markTestSkipped('no bundled illustration to serve');
        }

        $parts = explode('-', basename($files[0], '.avif'));
        $sci = ucfirst($parts[0]) . ' ' . implode(' ', array_slice($parts, 1));

        $res = $this->request('GET', '/api/illustration?sci=' . rawurlencode($sci));
        $this->assertSame(200, $res['status']);
        $this->assertSame('image/avif', $res['headers']['Content-Type'][0]);
    }

    public function testCutoutPlaceholderWhenMissing(): void
    {
        $res = $this->request('GET', '/api/illustration?sci=' . rawurlencode('Aaaa bbbb'));
        $this->assertSame(200, $res['status']);
        $this->assertStringContainsString('image/svg+xml', $res['headers']['Content-Type'][0]);
        $this->assertSame('not-generated', $res['headers']['X-Cutout-Status'][0]);
    }

    public function testCutoutRejectsInvalidSci(): void
    {
        $this->assertSame(400, $this->request('GET', '/api/illustration?sci=x')['status']);
    }

    public function testRecordingByScientificName(): void
    {
        $res = $this->request('GET', '/api/recording?sci=' . rawurlencode('Calypte anna'));
        $this->assertSame(200, $res['status']);
        $this->assertSame('audio/mpeg', $res['headers']['Content-Type'][0]);
    }

    public function testRecordingByFileName(): void
    {
        $file = 'Annas_Hummingbird-95-' . $this->today() . '.mp3';
        $res = $this->request('GET', '/api/recording?file=' . rawurlencode($file));
        $this->assertSame(200, $res['status']);
        $this->assertSame('audio/mpeg', $res['headers']['Content-Type'][0]);
    }

    public function testRecordingRejectsBadInput(): void
    {
        $this->assertSame(400, $this->request('GET', '/api/recording')['status']);
        $this->assertSame(
            400,
            $this->request('GET', '/api/recording?file=' . rawurlencode('../../etc/passwd'))['status'],
        );
        $this->assertSame(400, $this->request('GET', '/api/recording?file=notanmp3')['status']);
        $this->assertSame(404, $this->request('GET', '/api/recording?file=Missing-00-2020-01-01.mp3')['status']);
    }

    public function testSpectrogramByFileName(): void
    {
        $file = 'Annas_Hummingbird-95-' . $this->today() . '.png';
        $res = $this->request('GET', '/api/spectrogram?file=' . rawurlencode($file));
        $this->assertSame(200, $res['status']);
        $this->assertSame('image/png', $res['headers']['Content-Type'][0]);
    }

    public function testMenuOpenWhenAuthDisabled(): void
    {
        $res = $this->json('GET', '/api/menu');
        $this->assertSame(200, $res['status']);
        $this->assertNotEmpty($res['data']['items']);
    }

    public function testConfigGetWhenAuthDisabled(): void
    {
        $res = $this->json('GET', '/api/config');
        $this->assertSame(200, $res['status']);
        $this->assertSame('Test Garden', $res['data']['values']['SITE_NAME']);
        $this->assertSame(0.7, $res['data']['values']['CONFIDENCE']);
    }

    public function testConfigPostValidationRejectsOutOfRange(): void
    {
        $res = $this->json('POST', '/api/config', [], json_encode(['CONFIDENCE' => 5]));
        $this->assertSame(400, $res['status']);
        $this->assertArrayHasKey('CONFIDENCE', $res['data']['fields']);
    }

    public function testConfigPostWritesValidValue(): void
    {
        $write = $this->json('POST', '/api/config', [], json_encode(['SF_THRESH' => 0.2]));
        $this->assertSame(200, $write['status']);
        $this->assertTrue($write['data']['ok']);

        $read = $this->json('GET', '/api/config');
        $this->assertSame(0.2, $read['data']['values']['SF_THRESH']);
    }

    public function testStatusDiagWhenAuthDisabled(): void
    {
        $res = $this->json('GET', '/api/status?action=diag');
        $this->assertSame(200, $res['status']);
        $this->assertArrayHasKey('services', $res['data']);
    }
}
