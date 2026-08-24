<?php
declare(strict_types=1);

use Horeca\Bootstrap;
use Horeca\HorecaRepository;
use Horeca\Http;
use Horeca\TelegramAuth;

require dirname(__DIR__) . '/src/Bootstrap.php';
require dirname(__DIR__) . '/src/Http.php';
require dirname(__DIR__) . '/src/TelegramAuth.php';
require dirname(__DIR__) . '/src/HorecaRepository.php';

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
        $ok = $repository->updateJob((int) ($body['job_id'] ?? 0), (int) $user['id'], $isAdmin, $body);
        Http::json($ok ? 200 : 403, $ok
            ? ['status' => 'ok']
            : ['status' => 'error', 'error' => 'forbidden']);
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

