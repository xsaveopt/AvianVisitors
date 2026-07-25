<?php

declare(strict_types=1);

namespace AvianVisitors\Support;

final class Exposition
{
    /** @var list<string> */
    private array $lines = [];

    /** @var array<string, true> */
    private array $declared = [];

    /**
     * @param array<string, string> $labels
     */
    public function single(string $name, string $type, string $help, float|int|null $value, array $labels = []): void
    {
        if ($value === null) {
            return;
        }
        $this->family($name, $type, $help);
        $this->lines[] = $name . self::labels($labels) . ' ' . self::num($value);
    }

    /**
     * @param list<array{0: array<string, string>, 1: float|int}> $samples
     */
    public function series(string $name, string $type, string $help, array $samples): void
    {
        if ($samples === []) {
            return;
        }
        $this->family($name, $type, $help);
        foreach ($samples as [$labels, $value]) {
            $this->lines[] = $name . self::labels($labels) . ' ' . self::num($value);
        }
    }

    /**
     * @param array<string, int> $cumulative
     */
    public function histogram(string $name, string $help, array $cumulative, int $count, float $sum): void
    {
        $this->family($name, 'histogram', $help);
        foreach ($cumulative as $le => $value) {
            $this->lines[] = $name . '_bucket' . self::labels(['le' => $le]) . ' ' . self::num($value);
        }
        $this->lines[] = $name . '_bucket' . self::labels(['le' => '+Inf']) . ' ' . self::num($count);
        $this->lines[] = $name . '_sum ' . self::num($sum);
        $this->lines[] = $name . '_count ' . self::num($count);
    }

    public function raw(string $text): void
    {
        $trimmed = trim($text);
        if ($trimmed === '') {
            return;
        }
        $m = [];
        foreach (explode("\n", $trimmed) as $line) {
            $line = rtrim($line, "\r");
            if (preg_match('/^#\s*(HELP|TYPE)\s+(\S+)/', $line, $m) === 1) {
                $this->declared[$m[2]] = true;
            }
            $this->lines[] = $line;
        }
    }

    public function render(): string
    {
        return implode("\n", $this->lines) . "\n";
    }

    private function family(string $name, string $type, string $help): void
    {
        if (isset($this->declared[$name])) {
            return;
        }
        $this->declared[$name] = true;
        $this->lines[] = '# HELP ' . $name . ' ' . strtr($help, ["\\" => '\\\\', "\n" => '\\n']);
        $this->lines[] = '# TYPE ' . $name . ' ' . $type;
    }

    /**
     * @param array<string, string> $labels
     */
    private static function labels(array $labels): string
    {
        if ($labels === []) {
            return '';
        }
        $parts = [];
        foreach ($labels as $key => $value) {
            $escaped = strtr($value, ["\\" => '\\\\', '"' => '\\"', "\n" => '\\n']);
            $parts[] = $key . '="' . $escaped . '"';
        }
        return '{' . implode(',', $parts) . '}';
    }

    private static function num(float|int $value): string
    {
        if (is_int($value)) {
            return (string) $value;
        }
        if (is_nan($value)) {
            return 'NaN';
        }
        if (is_infinite($value)) {
            return $value > 0 ? '+Inf' : '-Inf';
        }
        $text = rtrim(rtrim(sprintf('%.6F', $value), '0'), '.');
        return $text === '' || $text === '-' ? '0' : $text;
    }
}
