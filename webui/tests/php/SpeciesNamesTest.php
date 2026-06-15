<?php

declare(strict_types=1);

namespace AvianVisitors\Tests;

use AvianVisitors\Config;
use AvianVisitors\Support\SpeciesNames;
use AvianVisitors\Tests\Support\Runtime;
use PHPUnit\Framework\TestCase;

final class SpeciesNamesTest extends TestCase
{
    private string $appDir;

    protected function setUp(): void
    {
        $this->appDir = sys_get_temp_dir() . '/av-names-' . getmypid() . '-' . uniqid();
        @mkdir($this->appDir . '/birdnet/model', 0o777, true);
    }

    protected function tearDown(): void
    {
        Runtime::rmrf($this->appDir);
    }

    private function names(): SpeciesNames
    {
        $config = new Config($this->appDir, $this->appDir . '/BirdSongs', $this->appDir . '/logs', 'admin', '', 'ua');
        return new SpeciesNames($config);
    }

    private function writeBirds(string $json): void
    {
        file_put_contents($this->appDir . '/birdnet/birds.json', $json);
    }

    public function testResolvesFromShortKeysAndUnderscoresSpaces(): void
    {
        $this->writeBirds(json_encode([['sci' => 'Calypte anna', 'com' => "Anna's Hummingbird"]]));
        $this->assertSame("Anna's_Hummingbird", $this->names()->commonFor('Calypte anna'));
    }

    public function testResolvesFromLongKeyVariants(): void
    {
        $this->writeBirds(json_encode([['scientificName' => 'Calypte anna', 'commonName' => 'Anna Hummingbird']]));
        $this->assertSame('Anna_Hummingbird', $this->names()->commonFor('Calypte anna'));
    }

    public function testIsCaseInsensitive(): void
    {
        $this->writeBirds(json_encode([['sci' => 'Calypte anna', 'com' => 'Anna Hummingbird']]));
        $this->assertSame('Anna_Hummingbird', $this->names()->commonFor('calypte ANNA'));
    }

    public function testFallsBackToLabelsFile(): void
    {
        file_put_contents(
            $this->appDir . '/birdnet/model/labels.txt',
            "Calypte anna_Anna's Hummingbird\nPasser domesticus_House Sparrow\n",
        );
        $this->assertSame('House_Sparrow', $this->names()->commonFor('Passer domesticus'));
    }

    public function testReturnsNullWhenUnknown(): void
    {
        $this->writeBirds(json_encode([['sci' => 'Calypte anna', 'com' => 'Anna Hummingbird']]));
        $this->assertNull($this->names()->commonFor('Nonexistent species'));
    }
}
