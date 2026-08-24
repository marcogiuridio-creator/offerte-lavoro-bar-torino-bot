<?php
declare(strict_types=1);

namespace Horeca;

use PDO;

final class WebhookHandler
{
    public function __construct(
        private readonly PDO $db,
        private readonly TelegramClient $telegram,
        private readonly array $config
    ) {}

    /** @param array<string,mixed> $update */
    public function handle(array $update): void
    {
        if (isset($update['callback_query']) && is_array($update['callback_query'])) {
            $this->handleCallback($update['callback_query']);
            return;
        }
        $message = $update['message'] ?? null;
        if (!is_array($message)) {
            return;
        }
        $chatId = $message['chat']['id'] ?? null;
        $text = trim((string) ($message['text'] ?? ''));
        if (!is_int($chatId) && !is_string($chatId)) {
            return;
        }

        $command = strtolower((string) strtok($text, " \n"));
        $command = preg_replace('/@[^\s]+$/', '', $command) ?? $command;
        if ($command === '/start' || $command === '/help') {
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => "👋 Benvenuto nel bot Offerte Lavoro Ho.Re.Ca. Torino.\n\n👤 Cerchi lavoro? Usa /registrati\n🏪 Cerchi personale? Usa /pubblica\n📋 Regole: /regole",
            ]);
        } elseif ($command === '/regole') {
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => "📌 Nel gruppo sono ammesse solo offerte di lavoro Ho.Re.Ca.\n\nChi cerca lavoro si registra gratuitamente con /registrati. I datori pubblicano con /pubblica per ottenere maggiore visibilità, candidature rapide e dashboard.",
            ]);
        } elseif ($command === '/registrati' || $command === '/pubblica') {
            $base = rtrim((string) ($this->config['app']['base_url'] ?? ''), '/');
            $page = $command === '/registrati' ? 'webapp/index.html' : 'webapp/pubblica.html';
            $label = $command === '/registrati' ? '👤 Apri registrazione candidato' : '📢 Apri modulo pubblicazione';
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => $command === '/registrati'
                    ? 'Registrati gratuitamente e ricevi offerte compatibili.'
                    : 'Pubblica con il bot: offerta più visibile, candidatura rapida e dashboard.',
                'reply_markup' => ['inline_keyboard' => [[['text' => $label, 'web_app' => ['url' => $base . '/' . $page]]]]],
            ]);
        }

        $webAppData = $message['web_app_data']['data'] ?? null;
        if (is_string($webAppData) && isset($message['from']) && is_array($message['from'])) {
            $this->handleWebAppData($message['from'], $chatId, $webAppData);
        }
    }

    /** @param array<string,mixed> $user */
    private function handleWebAppData(array $user, int|string $chatId, string $json): void
    {
        $data = json_decode($json, true, 32, JSON_THROW_ON_ERROR);
        if (!is_array($data)) {
            return;
        }
        $repository = new HorecaRepository($this->db);
        $action = (string) ($data['action'] ?? '');
        if ($action === 'save_candidate_profile') {
            $repository->saveCandidateProfile($user, $data);
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => '🎉 Profilo salvato. Riceverai le offerte compatibili con le tue preferenze.',
            ]);
            return;
        }
        if ($action !== 'publish_job_offer' || ($data['package'] ?? 'free') !== 'free') {
            return;
        }
        if (!$this->contactBelongsToAuthor((string) ($data['contact'] ?? ''), $user)) {
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => '🛡 Il contatto Telegram non coincide con l’account che sta pubblicando.',
            ]);
            return;
        }
        $result = $repository->createFreeJob(
            $user, $data, (int) ($this->config['limits']['rate_hours'] ?? 6),
            (int) ($this->config['limits']['daily_max'] ?? 2)
        );
        if (!($result['ok'] ?? false)) {
            $this->telegram->call('sendMessage', ['chat_id' => $chatId, 'text' => '⏳ ' . $result['error']]);
            return;
        }
        $jobId = (int) $result['job_id'];
        try {
            $groupId = (int) ($this->config['telegram']['group_id'] ?? 0);
            if ($groupId === 0) {
                throw new \RuntimeException('Gruppo Telegram non configurato.');
            }
            $username = trim((string) ($user['username'] ?? ''));
            $identity = $username !== '' ? '@' . self::html($username) : 'Profilo Telegram verificato';
            $message = "✅ <b>OFFERTA ORGANIZZATA CON IL BOT</b>\n"
                . '🏪 <b>' . self::html(mb_strtoupper((string) $data['business_name'])) . "</b>\n\n"
                . '💼 <b>Ruolo:</b> ' . self::html($data['role'] ?? '') . "\n"
                . '📍 <b>Zona:</b> ' . self::html($data['zone'] ?? '') . "\n"
                . '⏰ <b>Turni:</b> ' . self::html($data['shift'] ?? '') . "\n"
                . '💰 <b>Paga:</b> ' . self::html(($data['salary'] ?? '') ?: 'Trattabile') . "\n\n"
                . '📝 ' . self::html($data['description'] ?? '') . "\n\n"
                . '📞 <b>Contatto:</b> ' . self::html($data['contact'] ?? '') . "\n"
                . '👤 <b>Pubblicato da:</b> <a href="tg://user?id=' . (int) $user['id'] . '">' . $identity . '</a>';
            $sent = $this->telegram->call('sendMessage', [
                'chat_id' => $groupId, 'text' => $message, 'parse_mode' => 'HTML',
                'reply_markup' => ['inline_keyboard' => [
                    [['text' => '📩 Candidati in 1-Click', 'callback_data' => 'apply_start:' . $jobId]],
                    [['text' => '📊 Dashboard Candidati', 'url' => rtrim((string) $this->config['app']['base_url'], '/') . '/webapp/dashboard.html?job_id=' . $jobId]],
                ]],
            ]);
            $repository->attachMessage($jobId, (int) $sent['result']['message_id']);
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => "✅ Annuncio #{$jobId} pubblicato. Matching e dashboard sono attivi.",
            ]);
        } catch (\Throwable $error) {
            $repository->rollbackFreeJob($jobId, (int) $user['id']);
            throw $error;
        }
    }

    /** @param array<string,mixed> $user */
    private function contactBelongsToAuthor(string $contact, array $user): bool
    {
        if (preg_match('/\+?[0-9][0-9 .()-]{7,}/', $contact)) {
            return true;
        }
        $username = strtolower(ltrim((string) ($user['username'] ?? ''), '@'));
        return $username !== '' && strtolower(ltrim(trim($contact), '@')) === $username;
    }

    private static function html(mixed $value): string
    {
        return htmlspecialchars(trim((string) $value), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
    }

    /** @param array<string,mixed> $query */
    private function handleCallback(array $query): void
    {
        $callbackId = (string) ($query['id'] ?? '');
        $user = $query['from'] ?? null;
        $data = (string) ($query['data'] ?? '');
        if (!is_array($user) || !isset($user['id'])) {
            return;
        }
        $this->telegram->call('answerCallbackQuery', ['callback_query_id' => $callbackId]);
        $repository = new HorecaRepository($this->db);
        $candidateId = (int) $user['id'];
        $chatId = $candidateId;
        if (preg_match('/^apply_start:(\d+)$/', $data, $match)) {
            $jobId = (int) $match[1];
            if (!$repository->candidateProfile($candidateId)) {
                $base = rtrim((string) $this->config['app']['base_url'], '/');
                $this->telegram->call('sendMessage', [
                    'chat_id' => $chatId, 'text' => 'Prima crea gratuitamente il tuo profilo candidato.',
                    'reply_markup' => ['inline_keyboard' => [[['text' => '👤 Registrati', 'web_app' => ['url' => $base . '/webapp/index.html']]]]],
                ]);
                return;
            }
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId, 'text' => 'Sei disponibile a iniziare subito?',
                'reply_markup' => ['inline_keyboard' => [
                    [['text' => '✅ Disponibile', 'callback_data' => "apply_q1:{$jobId}:Disponibile"]],
                    [['text' => '⚠️ Da concordare', 'callback_data' => "apply_q1:{$jobId}:Da concordare"]],
                ]],
            ]);
            return;
        }
        if (preg_match('/^apply_q1:(\d+):(.+)$/', $data, $match)) {
            $jobId = (int) $match[1];
            if (!$repository->saveScreeningAnswer($candidateId, $jobId, 'screening_q1', $match[2])) {
                return;
            }
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId, 'text' => 'Hai HACCP valido o i requisiti richiesti?',
                'reply_markup' => ['inline_keyboard' => [
                    [['text' => '📜 Requisiti OK', 'callback_data' => "apply_q2:{$jobId}:HACCP OK"]],
                    [['text' => '⏳ Da rinnovare', 'callback_data' => "apply_q2:{$jobId}:Da rinnovare"]],
                ]],
            ]);
            return;
        }
        if (preg_match('/^apply_q2:(\d+):(.+)$/', $data, $match)) {
            $jobId = (int) $match[1];
            if (!$repository->saveScreeningAnswer($candidateId, $jobId, 'screening_q2', $match[2])) {
                return;
            }
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId, 'text' => 'Confermi l’invio della candidatura al titolare?',
                'reply_markup' => ['inline_keyboard' => [[
                    ['text' => '🚀 Invia candidatura', 'callback_data' => "apply_submit:{$jobId}"]
                ]]],
            ]);
            return;
        }
        if (preg_match('/^apply_submit:(\d+)$/', $data, $match)) {
            $jobId = (int) $match[1];
            $username = (string) ($user['username'] ?? '');
            $appId = $repository->submitApplication($candidateId, $jobId, $username);
            if (!$appId) {
                $this->telegram->call('sendMessage', ['chat_id' => $chatId, 'text' => 'Completa prima profilo e domande.']);
                return;
            }
            $job = $repository->job($jobId);
            $this->telegram->call('sendMessage', ['chat_id' => $chatId, 'text' => "✅ Candidatura inviata per l’offerta #{$jobId}."]);
            if ($job) {
                $this->telegram->call('sendMessage', [
                    'chat_id' => (int) $job['user_id'],
                    'text' => "📩 Nuova candidatura per l’offerta #{$jobId}. Apri la dashboard per valutarla.",
                ]);
            }
        }
    }
}
