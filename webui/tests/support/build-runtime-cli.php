<?php

declare(strict_types=1);

require __DIR__ . '/Runtime.php';

use AvianVisitors\Tests\Support\Runtime;

$base = $argv[1] ?? sys_get_temp_dir() . '/av-e2e';
echo Runtime::build($base);
