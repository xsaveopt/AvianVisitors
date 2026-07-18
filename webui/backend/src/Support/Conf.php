<?php

declare(strict_types=1);

namespace AvianVisitors\Support;

final class Conf
{
    public function __construct(
        private readonly string $path,
    ) {}

    /**
     * @return array<string, string>
     */
    public function read(): array
    {
        if (!is_readable($this->path)) {
            return [];
        }
        $out = [];
        $m = [];
        foreach (file($this->path, FILE_IGNORE_NEW_LINES) ?: [] as $line) {
            if (!$line || $line[0] === '#') {
                continue;
            }
            if (preg_match('/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$/i', $line, $m)) {
                $val = trim($m[2]);
                if (strlen($val) >= 2 && $val[0] === '"' && substr($val, -1) === '"') {
                    $val = substr($val, 1, -1);
                }
                $out[$m[1]] = $val;
            }
        }
        return $out;
    }

    /**
     * @param array<string, scalar|null> $updates
     */
    public function write(array $updates): bool
    {
        if (!is_writable($this->path) && !is_writable(dirname($this->path))) {
            return false;
        }
        $lines = is_readable($this->path) ? (file($this->path, FILE_IGNORE_NEW_LINES) ?: []) : [];
        $seen = [];
        $m = [];
        foreach ($lines as $i => $line) {
            if (!preg_match('/^\s*([A-Z_][A-Z0-9_]*)\s*=/i', $line, $m)) {
                continue;
            }
            $k = $m[1];
            if (array_key_exists($k, $updates)) {
                $lines[$i] = $k . '=' . $this->quote($updates[$k]);
                $seen[$k] = true;
            }
        }
        foreach ($updates as $k => $v) {
            if (!empty($seen[$k])) {
                continue;
            }
            $lines[] = $k . '=' . $this->quote($v);
        }
        $tmp = $this->path . '.tmp.' . (string) getmypid();
        if (file_put_contents($tmp, implode("\n", $lines) . "\n") === false) {
            return false;
        }
        return rename($tmp, $this->path);
    }

    private function quote(mixed $v): string
    {
        $s = (string) $v;
        if ($s === '' || preg_match('/[^A-Za-z0-9._\/+-]/', $s)) {
            return '"' . addcslashes($s, "\\\"\$`") . '"';
        }
        return $s;
    }
}
