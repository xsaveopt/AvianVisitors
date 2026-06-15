<?php

declare(strict_types=1);

namespace AvianVisitors;

use PDO;

final class Database
{
    private ?PDO $pdo = null;

    public function __construct(
        private readonly string $path,
    ) {}

    public function exists(): bool
    {
        return is_file($this->path);
    }

    public function pdo(): PDO
    {
        if ($this->pdo === null) {
            $this->pdo = new PDO('sqlite:' . $this->path, null, null, [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            ]);
        }
        return $this->pdo;
    }

    public function rows(string $sql, array $bind = []): array
    {
        $stmt = $this->pdo()->prepare($sql);
        foreach ($bind as $key => $value) {
            $stmt->bindValue($key, $value, match (true) {
                is_int($value) => PDO::PARAM_INT,
                is_bool($value) => PDO::PARAM_BOOL,
                is_null($value) => PDO::PARAM_NULL,
                default => PDO::PARAM_STR,
            });
        }
        $stmt->execute();
        return $stmt->fetchAll();
    }

    public function one(string $sql, array $bind = []): ?array
    {
        return $this->rows($sql, $bind)[0] ?? null;
    }

    public function value(string $sql, array $bind = []): mixed
    {
        $row = $this->one($sql, $bind);
        return $row === null ? null : array_values($row)[0];
    }
}
