<?php
declare(strict_types=1);

namespace Horeca;

use PDO;
use RuntimeException;

final class Bootstrap
{
    /** @return array<string,mixed> */
    public static function config(): array
    {
        static $config;
        if (is_array($config)) {
            return $config;
        }

        $path = dirname(__DIR__) . '/config/local.php';
        if (!is_file($path)) {
            throw new RuntimeException('Configurazione locale mancante.');
        }

        $loaded = require $path;
        if (!is_array($loaded)) {
            throw new RuntimeException('Configurazione locale non valida.');
        }
        date_default_timezone_set((string) ($loaded['app']['timezone'] ?? 'Europe/Rome'));
        return $config = $loaded;
    }

    public static function db(): PDO
    {
        static $pdo;
        if ($pdo instanceof PDO) {
            return $pdo;
        }

        $db = self::config()['database'] ?? [];
        foreach (['host', 'name', 'username', 'password'] as $key) {
            if (!isset($db[$key]) || $db[$key] === '') {
                throw new RuntimeException('Configurazione database incompleta.');
            }
        }
        $charset = (string) ($db['charset'] ?? 'utf8mb4');
        $dsn = sprintf(
            'mysql:host=%s;port=%d;dbname=%s;charset=%s',
            $db['host'],
            (int) ($db['port'] ?? 3306),
            $db['name'],
            $charset
        );
        return $pdo = new PDO($dsn, (string) $db['username'], (string) $db['password'], [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);
    }
}

