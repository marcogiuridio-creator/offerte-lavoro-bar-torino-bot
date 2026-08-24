<?php
declare(strict_types=1);

$root = dirname(__DIR__);
$required = [
    '/api/telegram-webhook.php',
    '/api/health.php',
    '/config/config.example.php',
    '/database/schema.sql',
    '/src/Bootstrap.php',
    '/src/TelegramClient.php',
    '/src/UpdateRepository.php',
    '/src/WebhookHandler.php',
];
foreach ($required as $file) {
    if (!is_file($root . $file)) {
        fwrite(STDERR, "File mancante: {$file}\n");
        exit(1);
    }
}

$config = require $root . '/config/config.example.php';
foreach (['app', 'telegram', 'database'] as $section) {
    if (!isset($config[$section]) || !is_array($config[$section])) {
        fwrite(STDERR, "Sezione configurazione mancante: {$section}\n");
        exit(1);
    }
}
echo "horeca smoke: ok\n";

