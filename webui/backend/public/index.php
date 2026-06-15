<?php

declare(strict_types=1);

use AvianVisitors\Config;
use AvianVisitors\Kernel;

require dirname(__DIR__, 2) . '/vendor/autoload.php';

Kernel::create(Config::fromEnv())->run();
