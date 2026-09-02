<?php
declare(strict_types=1);

use Horeca\Bootstrap;
use Horeca\HorecaRepository;
use Horeca\Http;
use Horeca\TelegramAuth;
use Horeca\TelegramClient;

require dirname(__DIR__) . '/src/Bootstrap.php';
require dirname(__DIR__) . '/src/Http.php';
require dirname(__DIR__) . '/src/TelegramAuth.php';
require dirname(__DIR__) . '/src/HorecaRepository.php';
require dirname(__DIR__) . '/src/TelegramClient.php';

try {
    $config = Bootstrap::config();
    $user = TelegramAuth::validate(
        (string) ($_SERVER['HTTP_X_TELEGRAM_INIT_DATA'] ?? ''),
        (string) ($config['telegram']['bot_token'] ?? '')
    );
    if (!$user) {
        Http::json(401, ['status' => 'error', 'error' => 'unauthorized']);
    }
    $repository = new HorecaRepository(Bootstrap::db());
    $route = trim((string) ($_GET['route'] ?? ''), '/');
    $method = strtoupper((string) ($_SERVER['REQUEST_METHOD'] ?? 'GET'));
    $adminIds = array_map('intval', $config['telegram']['admin_ids'] ?? []);
    $isAdmin = in_array((int) $user['id'], $adminIds, true);

    if ($method === 'GET' && $route === 'get_profile') {
        $profile = $repository->candidateProfile((int) $user['id']);
        Http::json(200, ['status' => 'ok', 'profile' => $profile]);
    }
    if ($method === 'GET' && $route === 'get_job_offer') {
        $job = $repository->job((int) ($_GET['job_id'] ?? 0));
        if (!$job || (!$isAdmin && (int) $job['user_id'] !== (int) $user['id'])) {
            Http::json(403, ['status' => 'error', 'error' => 'forbidden']);
        }
        Http::json(200, ['status' => 'ok', 'job' => $job]);
    }
    if ($method === 'GET' && $route === 'get_employer_candidates') {
        $rows = $repository->employerCandidates(
            (int) ($_GET['job_id'] ?? 0), (int) $user['id'], $isAdmin
        );
        Http::json(200, ['status' => 'ok', 'candidates' => $rows]);
    }

    $raw = file_get_contents('php://input');
    $body = json_decode(is_string($raw) ? $raw : '', true);
    if (!is_array($body)) {
        Http::json(400, ['status' => 'error', 'error' => 'invalid_body']);
    }
    if ($method === 'POST' && $route === 'save_profile') {
        $repository->saveCandidateProfile($user, $body);
        Http::json(200, ['status' => 'ok']);
    }
    if ($method === 'POST' && $route === 'update_job_offer') {
        $jobId = (int) ($body['job_id'] ?? 0);
        $previous = $repository->job($jobId);
        $ok = $repository->updateJob($jobId, (int) $user['id'], $isAdmin, $body);
        if (!$ok || !$previous) {
            Http::json(403, ['status' => 'error', 'error' => 'forbidden']);
        }
        $updated = $repository->job($jobId);
        try {
            if ($updated && (int) ($updated['message_id'] ?? 0) > 0) {
                $telegram = new TelegramClient((string) ($config['telegram']['bot_token'] ?? ''));
                $username = trim((string) ($updated['username'] ?? $user['username'] ?? ''));
                $identity = $username !== '' ? '@' . html($username) : 'Profilo Telegram verificato';
                $header = in_array((string) ($updated['package'] ?? 'base'), ['evidenza', 'vip', 'vip_mensile'], true)
                    ? '🌟 <b>OFFERTA SPONSOR VERIFICATA</b>'
                    : '✅ <b>OFFERTA ORGANIZZATA CON IL BOT</b>';
                $text = $header . "\n🏪 <b>" . html(mb_strtoupper((string) $updated['business_name'])) . "</b>\n\n"
                    . '💼 <b>Ruolo:</b> ' . html($updated['role']) . "\n"
                    . '📍 <b>Zona:</b> ' . html($updated['zone']) . "\n"
                    . '⏰ <b>Turni:</b> ' . html($updated['shift']) . "\n"
                    . '💰 <b>Paga:</b> ' . html($updated['salary'] ?: 'Trattabile') . "\n\n"
                    . '📝 ' . html($updated['description']) . "\n\n"
                    . '📞 <b>Contatto:</b> ' . html($updated['contact']) . "\n"
                    . '👤 <b>Pubblicato da:</b> <a href="tg://user?id=' . (int) $updated['user_id'] . '">' . $identity . '</a>'
                    . "\n\n✏️ <i>Annuncio aggiornato dal datore</i>";
                $base = rtrim((string) ($config['app']['base_url'] ?? ''), '/');
                $telegram->call('editMessageText', [
                    'chat_id' => (int) ($config['telegram']['group_id'] ?? 0),
                    'message_id' => (int) $updated['message_id'],
                    'text' => $text,
                    'parse_mode' => 'HTML',
                    'reply_markup' => ['inline_keyboard' => [
                        [['text' => '📩 Candidati in 1-Click', 'callback_data' => 'apply_start:' . $jobId]],
                        [['text' => '📊 Dashboard Candidati', 'url' => $base . '/webapp/dashboard.html?job_id=' . $jobId]],
                    ]],
                ]);
            }
        } catch (Throwable $error) {
            // Database e messaggio Telegram devono restare sincronizzati.
            $repository->updateJob($jobId, (int) $previous['user_id'], true, $previous);
            throw $error;
        }
        Http::json(200, ['status' => 'ok', 'message_updated' => (int) ($updated['message_id'] ?? 0) > 0]);
    }
    if ($method === 'POST' && $route === 'update_application_status') {
        $ok = $repository->updateApplicationStatus(
            (int) ($body['app_id'] ?? 0), (int) $user['id'], (string) ($body['status'] ?? '')
        );
        Http::json($ok ? 200 : 400, $ok
            ? ['status' => 'ok']
            : ['status' => 'error', 'error' => 'invalid_request']);
    }
    Http::json(404, ['status' => 'error', 'error' => 'not_found']);
} catch (Throwable $error) {
    error_log('horeca api error: ' . $error->getMessage());
    Http::json(500, ['status' => 'error', 'error' => 'internal_error']);
}

function html(mixed $value): string
{
    return htmlspecialchars(trim((string) $value), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}
