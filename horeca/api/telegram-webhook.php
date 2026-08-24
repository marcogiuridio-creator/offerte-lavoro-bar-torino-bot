<?php
declare(strict_types=1);

use Horeca\Bootstrap;
use Horeca\Http;
use Horeca\TelegramClient;
use Horeca\UpdateRepository;
use Horeca\WebhookHandler;

require dirname(__DIR__) . '/src/Bootstrap.php';
require dirname(__DIR__) . '/src/Http.php';
require dirname(__DIR__) . '/src/TelegramClient.php';
require dirname(__DIR__) . '/src/UpdateRepository.php';
require dirname(__DIR__) . '/src/HorecaRepository.php';
require dirname(__DIR__) . '/src/WebhookHandler.php';
require dirname(__DIR__) . '/src/CronRunner.php';

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'GET') {
    Http::json(200, ['status' => 'ok', 'service' => 'horeca-telegram-webhook']);
}

try {
    $config = Bootstrap::config();
    $expected = (string) ($config['telegram']['webhook_secret'] ?? '');
    $provided = (string) ($_SERVER['HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN'] ?? '');
    if ($expected === '' || !hash_equals($expected, $provided)) {
        Http::json(401, ['status' => 'error', 'error' => 'unauthorized']);
    }

    $raw = file_get_contents('php://input');
    if (!is_string($raw) || strlen($raw) > 1048576) {
        Http::json(400, ['status' => 'error', 'error' => 'invalid_body']);
    }
    $update = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
    if (!is_array($update) || !isset($update['update_id'])) {
        Http::json(400, ['status' => 'error', 'error' => 'invalid_update']);
    }

    $repository = new UpdateRepository(Bootstrap::db());
    $updateId = (int) $update['update_id'];
    if (!$repository->claim($updateId)) {
        Http::json(200, ['status' => 'ok', 'duplicate' => true]);
    }

    $telegram = new TelegramClient((string) $config['telegram']['bot_token']);
    (new WebhookHandler(Bootstrap::db(), $telegram, $config))->handle($update);
    // Esegue in modo idempotente scadenze, bump VIP e riepilogo giornaliero
    // anche sugli hosting condivisi senza un daemon sempre acceso.
    (new \Horeca\CronRunner(Bootstrap::db(), $telegram, $config))->run();
    $repository->markProcessed($updateId);
    Http::json(200, ['status' => 'ok']);
} catch (Throwable $error) {
    error_log('horeca webhook error: ' . $error->getMessage());
    Http::json(500, ['status' => 'error', 'error' => 'internal_error']);
}
