<?php
declare(strict_types=1);

use Horeca\Bootstrap;
use Horeca\Http;

require dirname(__DIR__) . '/src/Bootstrap.php';
require dirname(__DIR__) . '/src/Http.php';

try {
    Bootstrap::db()->query('SELECT 1');
    Http::json(200, ['status' => 'ok', 'database' => 'ok']);
} catch (Throwable $error) {
    error_log('horeca health error: ' . $error->getMessage());
    Http::json(503, ['status' => 'error', 'database' => 'unavailable']);
}

