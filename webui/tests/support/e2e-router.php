<?php

declare(strict_types=1);

$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH) ?: '/';

if (str_starts_with($path, '/api')) {
    require dirname(__DIR__, 2) . '/backend/public/index.php';
    return true;
}

$dist = $_SERVER['DOCUMENT_ROOT'];
if ($path !== '/' && is_file($dist . $path)) {
    return false;
}

header('Content-Type: text/html; charset=utf-8');
readfile($dist . '/index.html');
return true;
