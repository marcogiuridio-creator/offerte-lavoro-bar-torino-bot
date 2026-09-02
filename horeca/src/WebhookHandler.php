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
        if (isset($update['pre_checkout_query']) && is_array($update['pre_checkout_query'])) {
            $this->handlePreCheckout($update['pre_checkout_query']);
            return;
        }
        if (isset($update['callback_query']) && is_array($update['callback_query'])) {
            $this->handleCallback($update['callback_query']);
            return;
        }
        $message = $update['message'] ?? null;
        if (!is_array($message)) {
            return;
        }
        $chatId = $message['chat']['id'] ?? null;
        // Gli annunci arrivano sia come testo sia come didascalia di foto,
        // locandine e documenti. Telegram usa due campi distinti.
        $text = trim((string) ($message['text'] ?? $message['caption'] ?? ''));
        if (!is_int($chatId) && !is_string($chatId)) {
            return;
        }

        if (isset($message['successful_payment']) && is_array($message['successful_payment'])
            && isset($message['from']['id'])) {
            $this->handleSuccessfulPayment($message['from'], $chatId, $message['successful_payment']);
            return;
        }

        $command = strtolower((string) strtok($text, " \n"));
        $command = preg_replace('/@[^\s]+$/', '', $command) ?? $command;
        $argument = trim((string) substr($text, strlen((string) strtok($text, " \n"))));
        $mustDeleteGroupCommand = str_starts_with($command, '/')
            && (int) $chatId === (int) ($this->config['telegram']['group_id'] ?? 0)
            && isset($message['message_id']);

        try {
            if ($command === '/start' && in_array(strtolower($argument), ['pubblica', 'offerta'], true)) {
            $this->sendPublishLauncher($chatId, (string) ($message['chat']['type'] ?? 'private'));
            } elseif ($command === '/start' || $command === '/help') {
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => "👋 Benvenuto nel bot Offerte Lavoro Ho.Re.Ca. Torino.\n\n👤 Cerchi lavoro? Usa /registrati\n🏪 Cerchi personale? Usa /pubblica\n📋 Regole: /regole",
            ]);
            } elseif ($command === '/regole') {
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => "📌 Nel gruppo sono ammesse solo offerte di lavoro Ho.Re.Ca.\n\nChi cerca lavoro si registra gratuitamente con /registrati. I datori pubblicano con /pubblica per ottenere maggiore visibilità, candidature rapide e dashboard.",
            ]);
            } elseif ($command === '/pubblica' || $command === '/offerta') {
            $this->sendPublishLauncher($chatId, (string) ($message['chat']['type'] ?? 'private'));
            } elseif ($command === '/registrati') {
            $base = rtrim((string) ($this->config['app']['base_url'] ?? ''), '/');
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => 'Registrati gratuitamente e ricevi offerte compatibili.',
                'reply_markup' => ['inline_keyboard' => [[['text' => '👤 Apri registrazione candidato', 'web_app' => ['url' => $base . '/webapp/index.html']]]]],
            ]);
            } elseif ($command === '/profilo') {
            $this->sendProfile((array) ($message['from'] ?? []), $chatId);
            } elseif ($command === '/mie_offerte') {
            $this->sendUserOffers((array) ($message['from'] ?? []), $chatId);
            } elseif ($command === '/premium') {
            $this->sendPremium((array) ($message['from'] ?? []), $chatId);
            } elseif ($command === '/stats' && $this->isAdmin((int) ($message['from']['id'] ?? 0))) {
            $totals = (new HorecaRepository($this->db))->totals();
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => "📊 <b>Statistiche bot</b>\n\n👥 Utenti: {$totals['users']}\n📢 Offerte: {$totals['offers']}\n👤 Profili: {$totals['candidates']}\n📩 Candidature: {$totals['applications']}",
                'parse_mode' => 'HTML',
            ]);
            }
        } finally {
            // La pulizia non deve dipendere dal successo della risposta al comando:
            // anche se Telegram rifiuta il messaggio del bot, il comando di servizio
            // inserito nel gruppo deve sparire dopo sette secondi.
            if ($mustDeleteGroupCommand) {
                $this->deleteGroupCommandAfterDelay($chatId, (int) $message['message_id']);
            }
        }

        $webAppData = $message['web_app_data']['data'] ?? null;
        if (is_string($webAppData) && isset($message['from']) && is_array($message['from'])) {
            $this->handleWebAppData($message['from'], $chatId, $webAppData);
            return;
        }
        if ($text !== '' && !str_starts_with($text, '/')
            && isset($message['from']) && is_array($message['from'])) {
            $this->handleAutomaticOffer($message, $message['from'], $chatId, $text);
        }
    }

    private function sendPublishLauncher(int|string $chatId, string $chatType): void
    {
        $base = rtrim((string) ($this->config['app']['base_url'] ?? ''), '/');
        $label = '📢 Apri modulo pubblicazione';
        if ($chatType !== 'private') {
            $username = ltrim((string) ($this->config['telegram']['bot_username'] ?? 'lavorotorinobot'), '@');
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => 'Per pubblicare apri la chat privata con il bot.',
                'reply_markup' => ['inline_keyboard' => [[[
                    'text' => '💬 Apri il bot e pubblica',
                    'url' => 'https://t.me/' . $username . '?start=pubblica',
                ]]]],
            ]);
            return;
        }

        // Telegram.WebApp.sendData funziona con le Mini App aperte da una
        // reply keyboard. Il webhook ricevera quindi web_app_data e pubblichera
        // l'annuncio con lo stesso flusso autenticato gia in uso.
        $this->telegram->call('sendMessage', [
            'chat_id' => $chatId,
            'text' => 'Compila il modulo: al termine il bot pubblicherà l’annuncio e ti confermerà il numero dell’offerta.',
            'reply_markup' => [
                'keyboard' => [[['text' => $label, 'web_app' => ['url' => $base . '/webapp/pubblica.html']]]],
                'resize_keyboard' => true,
                'one_time_keyboard' => true,
            ],
        ]);
    }

    /** @param array<string,mixed> $user */
    private function sendProfile(array $user, int|string $chatId): void
    {
        if (!isset($user['id'])) {
            return;
        }
        $profile = (new HorecaRepository($this->db))->candidateProfile((int) $user['id']);
        $base = rtrim((string) ($this->config['app']['base_url'] ?? ''), '/');
        if (!$profile) {
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId, 'text' => 'Non hai ancora un profilo candidato.',
                'reply_markup' => ['inline_keyboard' => [[[
                    'text' => '👤 Crea il profilo gratuito', 'web_app' => ['url' => $base . '/webapp/index.html'],
                ]]]],
            ]);
            return;
        }
        $premium = (int) ($profile['is_premium'] ?? 0) === 1
            && !empty($profile['premium_until'])
            && new \DateTimeImmutable((string) $profile['premium_until']) > new \DateTimeImmutable('now');
        $status = $premium ? '⭐ Premium fino al ' . $profile['premium_until'] : '⚪ Base gratuito';
        $this->telegram->call('sendMessage', [
            'chat_id' => $chatId,
            'text' => "👤 <b>Il tuo profilo</b>\n\nNome: " . self::html($profile['first_name'] ?? '')
                . "\nStato: " . self::html($status) . "\n\nPuoi aggiornare ruoli, esperienza e disponibilità.",
            'parse_mode' => 'HTML',
            'reply_markup' => ['inline_keyboard' => [[[
                'text' => '✏️ Modifica profilo', 'web_app' => ['url' => $base . '/webapp/index.html'],
            ]]]],
        ]);
    }

    /** @param array<string,mixed> $user */
    private function sendUserOffers(array $user, int|string $chatId): void
    {
        if (!isset($user['id'])) {
            return;
        }
        $offers = (new HorecaRepository($this->db))->userOffers((int) $user['id']);
        if (!$offers) {
            $this->telegram->call('sendMessage', ['chat_id' => $chatId, 'text' => '📋 Non hai ancora pubblicato offerte. Usa /pubblica.']);
            return;
        }
        $base = rtrim((string) ($this->config['app']['base_url'] ?? ''), '/');
        foreach ($offers as $offer) {
            $jobId = (int) $offer['job_id'];
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => '🏪 <b>' . self::html(mb_strtoupper((string) $offer['business_name'])) . '</b>'
                    . "\n💼 " . self::html($offer['role']) . "\n🆔 Offerta #{$jobId}",
                'parse_mode' => 'HTML',
                'reply_markup' => ['inline_keyboard' => [[[
                    'text' => '📊 Dashboard candidati',
                    'url' => $base . '/webapp/dashboard.html?job_id=' . $jobId,
                ]]]],
            ]);
        }
    }

    /** @param array<string,mixed> $user */
    private function sendPremium(array $user, int|string $chatId): void
    {
        $profile = isset($user['id']) ? (new HorecaRepository($this->db))->candidateProfile((int) $user['id']) : null;
        if (!$profile) {
            $this->telegram->call('sendMessage', ['chat_id' => $chatId, 'text' => 'Crea prima il profilo gratuito con /registrati.']);
            return;
        }
        $this->telegram->call('sendMessage', [
            'chat_id' => $chatId,
            'text' => "💎 <b>CANDIDATO PREMIUM</b>\n\n⚡ Notifiche immediate delle offerte compatibili\n⭐ Profilo mostrato prima ai titolari\n🏷️ Badge Premium\n\nCosto: 100 Telegram Stars per 30 giorni.",
            'parse_mode' => 'HTML',
            'reply_markup' => ['inline_keyboard' => [[[
                'text' => '🌟 Attiva con 100 Stars', 'callback_data' => 'pay_stars',
            ]]]],
        ]);
    }

    /** @param array<string,mixed> $query */
    private function handlePreCheckout(array $query): void
    {
        $payload = (string) ($query['invoice_payload'] ?? '');
        $currency = (string) ($query['currency'] ?? '');
        $amount = (int) ($query['total_amount'] ?? 0);
        $userId = (int) ($query['from']['id'] ?? 0);
        $repository = new HorecaRepository($this->db);
        $valid = ($payload === 'premium_subscription_stars' && $currency === 'XTR' && $amount === 100
            && $userId > 0 && $repository->candidateProfile($userId) !== null)
            || $repository->validJobCheckout($userId, $payload, $currency, $amount);
        $parameters = ['pre_checkout_query_id' => (string) ($query['id'] ?? ''), 'ok' => $valid];
        if (!$valid) {
            $parameters['error_message'] = 'Pagamento non riconosciuto oppure profilo candidato mancante.';
        }
        $this->telegram->call('answerPreCheckoutQuery', $parameters);
    }

    /** @param array<string,mixed> $user @param array<string,mixed> $payment */
    private function handleSuccessfulPayment(array $user, int|string $chatId, array $payment): void
    {
        $repository = new HorecaRepository($this->db);
        $payload = (string) ($payment['invoice_payload'] ?? '');
        if (str_starts_with($payload, 'job_offer_id_')) {
            $job = $repository->activatePaidJobPayment(
                (int) $user['id'], (string) ($payment['telegram_payment_charge_id'] ?? ''), $payload,
                (string) ($payment['currency'] ?? ''), (int) ($payment['total_amount'] ?? 0)
            );
            if (!$job) return;
            $groupId = (int) ($this->config['telegram']['group_id'] ?? 0);
            $sent = $this->telegram->call('sendMessage', [
                'chat_id'=>$groupId,'text'=>$this->offerMessage($job, $user, true),'parse_mode'=>'HTML',
                'reply_markup'=>['inline_keyboard'=>[
                    [['text'=>'📩 Candidati in 1-Click','callback_data'=>'apply_start:' . (int) $job['job_id']]],
                    [['text'=>'📊 Dashboard Candidati','url'=>rtrim((string) $this->config['app']['base_url'],'/') . '/webapp/dashboard.html?job_id=' . (int) $job['job_id']]],
                ]],
            ]);
            $messageId = (int) ($sent['result']['message_id'] ?? 0);
            $repository->attachMessage((int) $job['job_id'], $messageId);
            $this->telegram->call('pinChatMessage', ['chat_id'=>$groupId,'message_id'=>$messageId,'disable_notification'=>true]);
            foreach ($repository->activePremiumCandidates() as $candidate) {
                try {
                    $this->telegram->call('sendMessage', [
                        'chat_id'=>(int) $candidate['user_id'],
                        'text'=>'⚡ Nuova offerta Premium: ' . self::html($job['role']) . ' · ' . self::html($job['zone']),
                        'reply_markup'=>['inline_keyboard'=>[[['text'=>'📩 Candidati ora','callback_data'=>'apply_start:' . (int) $job['job_id']]]]],
                    ]);
                } catch (\Throwable $error) { error_log('premium push skipped: ' . $error->getMessage()); }
            }
            $this->telegram->call('sendMessage', ['chat_id'=>$chatId,'text'=>'✅ Pagamento ricevuto. Annuncio #' . (int) $job['job_id'] . ' pubblicato e promosso.']);
            return;
        }
        $expiry = $repository->activatePremiumPayment(
            (int) $user['id'], (string) ($payment['telegram_payment_charge_id'] ?? ''),
            $payload, (string) ($payment['currency'] ?? ''),
            (int) ($payment['total_amount'] ?? 0)
        );
        if ($expiry === null) {
            return;
        }
        $this->telegram->call('sendMessage', [
            'chat_id' => $chatId,
            'text' => '🎉 Pagamento ricevuto. Premium attivo fino al <b>' . self::html($expiry) . '</b>.',
            'parse_mode' => 'HTML',
        ]);
    }

    private function isAdmin(int $userId): bool
    {
        return in_array($userId, array_map('intval', (array) ($this->config['telegram']['admin_ids'] ?? [])), true);
    }

    /** @param array<string,mixed> $message @param array<string,mixed> $user */
    private function handleAutomaticOffer(array $message, array $user, int|string $chatId, string $text): void
    {
        $groupId = (int) ($this->config['telegram']['group_id'] ?? 0);
        if ($groupId === 0 || (int) $chatId !== $groupId || !$this->looksLikeJobOffer($text)
            || !isset($message['message_id'], $user['id'])) {
            return;
        }
        $repository = new HorecaRepository($this->db);
        $fields = $this->automaticFields($text, $user);
        $result = $repository->createFreeJob(
            $user, $fields, (int) ($this->config['limits']['automatic_rate_hours'] ?? 0),
            (int) ($this->config['limits']['automatic_daily_max'] ?? 10)
        );
        if (!($result['ok'] ?? false)) {
            error_log('horeca automatic conversion skipped by quota: user_id=' . (int) $user['id']);
            return;
        }
        $jobId = (int) $result['job_id'];
        $publishedMessageId = 0;
        try {
            $sent = $this->telegram->call('sendMessage', [
                'chat_id' => $groupId,
                'text' => $this->automaticOfferText($fields, $user),
                'parse_mode' => 'HTML',
                'reply_markup' => ['inline_keyboard' => [
                    [['text' => '📩 Candidati in 1-Click', 'callback_data' => 'apply_start:' . $jobId]],
                    [['text' => '💬 Contatta l’autore verificato', 'url' => 'tg://user?id=' . (int) $user['id']]],
                    [['text' => '📊 Dashboard Candidati', 'url' => rtrim((string) $this->config['app']['base_url'], '/') . '/webapp/dashboard.html?job_id=' . $jobId]],
                ]],
            ]);
            $publishedMessageId = (int) ($sent['result']['message_id'] ?? 0);
            if ($publishedMessageId <= 0) {
                throw new \RuntimeException('Telegram non ha restituito il messaggio pubblicato.');
            }
            $this->telegram->call('deleteMessage', [
                'chat_id' => $groupId, 'message_id' => (int) $message['message_id'],
            ]);
            $repository->recordAutomaticConversion(
                $user, $chatId, (int) $message['message_id'], $publishedMessageId, $jobId, $text
            );
            $repository->attachMessage($jobId, $publishedMessageId);
        } catch (\Throwable $error) {
            if ($publishedMessageId > 0) {
                try {
                    $this->telegram->call('deleteMessage', [
                        'chat_id' => $groupId, 'message_id' => $publishedMessageId,
                    ]);
                } catch (\Throwable) {
                }
            }
            $repository->rollbackFreeJob($jobId, (int) $user['id']);
            error_log('horeca automatic conversion rollback: ' . $error->getMessage());
        }
    }

    private function looksLikeJobOffer(string $text): bool
    {
        $normalized = preg_replace('/\\s+/u', ' ', mb_strtolower(trim($text))) ?? mb_strtolower(trim($text));

        // Evita i falsi positivi piu comuni dei candidati, pur permettendo a un
        // datore di scrivere in prima persona: "cerco un cameriere".
        $candidateIntent = preg_match('/\\b(cerco|cerca|sto\\s+cercando|sono\\s+in\\s+cerca\\s+di)\\s+(?:un\\s+)?(?:lavoro|impiego|occupazione)|\\bmi\\s+candido|\\bcandidatura\\s+(?:come|per)|\\bdisponibile\\s+(?:da|come)\\b/u', $normalized) === 1;
        if ($candidateIntent) {
            return false;
        }

        $intent = preg_match('/\\b(?:cercasi|cerchiamo|ricerchiamo|assumiamo|selezioniamo|selezione\\s+(?:aperta|personale)|si\\s+cerca|si\\s+ricerca|si\\s+seleziona|stiamo\\s+cercando|stiamo\\s+selezionando|siamo\\s+alla\\s+ricerca|serve|servono|servirebbe|servirebbero|mi\\s+servirebbe|mi\\s+servirebbero|avrei\\s+bisogno|avremmo\\s+bisogno|abbiamo\\s+bisogno|c(?:’|\\x{27})?e\\s+bisogno|necessitiamo|occorrerebbe|occorrerebbero|offerta\\s+di\\s+lavoro|opportunit[aà]\\s+(?:di\\s+)?lavoro|posizione\\s+aperta|ricerca\\s+(?:di\\s+)?personale|personale\\s+(?:ricercato|richiesto)|nuov[ea]\\s+assunzion[ei]|inseriamo|da\\s+inserire|cerc[oa]\\s+(?:un|una|due|tre|\\d+)\\b)/u', $normalized) === 1;
        $role = preg_match('/\\b(?:barist[ai]|barman|barmen|barlady|bartender|barback|camerier[aei]|runner|commis(?:\\s+di\\s+sala)?|chef\\s+de\\s+rang|demi\\s+chef|cuoc[oa]|cuochi|aiut[oa]\\s+(?:cuoc[oa]|cucina)|lavapiatti|plongeur|pizzaiol[aei]|pasticcier[aei]|chef|sous\\s+chef|sushiman|grigliator[ei]|gelatier[aei]|panettier[aei]|rosticcier[ei]|banconist[aei]|cassier[aei]|sommelier|hostess|steward|receptionist|ma[iî]tre|restaurant\\s+manager|bar\\s+manager|store\\s+manager|direttor[ei]\\s+(?:di\\s+)?(?:sala|ristorante)|responsabile\\s+(?:di\\s+)?(?:sala|bar|cucina)|supervisor|addett[oaie]*\\s+(?:di\\s+|alla\\s+|alle\\s+)?(?:sala|bar|cucina|caffetteria|colazioni|accoglienza)|personale\\s+(?:di\\s+)?(?:sala|bar|cucina|ristorazione)|staff\\s+(?:di\\s+)?(?:sala|bar|cucina)|facchin[oi]|tuttofare)\\b/u', $normalized) === 1;
        return $intent && $role;
    }

    private function deleteGroupCommandAfterDelay(int|string $chatId, int $messageId): void
    {
        // Mantiene visibile il comando abbastanza a lungo da far capire all'utente
        // che è stato ricevuto, senza lasciare comandi di servizio nella chat.
        usleep(7_000_000);
        try {
            $this->telegram->call('deleteMessage', [
                'chat_id' => $chatId,
                'message_id' => $messageId,
            ]);
        } catch (\Throwable $error) {
            error_log('horeca command cleanup skipped: ' . $error->getMessage());
        }
    }

    /** @param array<string,mixed> $user @return array<string,string> */
    private function automaticFields(string $text, array $user): array
    {
        $roles = [
            '/\\b(?:barman|barmen|barlady|bartender)\\b/u' => 'Bartender / Barman',
            '/\\bbarback\\b/u' => 'Barback',
            '/\\bbarist[ai]\\b/u' => 'Barista', '/\\bcamerier[aei]\\b/u' => 'Cameriere/a',
            '/\\b(?:runner|commis(?:\\s+di\\s+sala)?|chef\\s+de\\s+rang|demi\\s+chef|addett[oaie]*\\s+(?:di\\s+|alla\\s+)?sala)\\b/u' => 'Personale di sala',
            '/\\b(?:ma[iî]tre|restaurant\\s+manager|direttor[ei]\\s+(?:di\\s+)?(?:sala|ristorante)|responsabile\\s+(?:di\\s+)?sala)\\b/u' => 'Responsabile di sala / Maître',
            '/\\b(?:bar\\s+manager|responsabile\\s+(?:di\\s+)?bar)\\b/u' => 'Bar Manager',
            '/\\b(?:cuoc[oa]|cuochi|chef|sous\\s+chef|aiut[oa]\\s+(?:cuoc[oa]|cucina))\\b/u' => 'Cuoco / Aiuto Cuoco',
            '/\\b(?:lavapiatti|plongeur)\\b/u' => 'Lavapiatti', '/\\bpizzaiol[aei]\\b/u' => 'Pizzaiolo/a',
            '/\\bpasticcier[aei]\\b/u' => 'Pasticciere/a', '/\\bsommelier\\b/u' => 'Sommelier',
            '/\\b(?:hostess|steward|addett[oaie]*\\s+(?:all(?:a|e)\\s+)?accoglienza)\\b/u' => 'Accoglienza',
            '/\\breceptionist\\b/u' => 'Receptionist',
        ];
        $role = 'Personale Horeca';
        foreach ($roles as $pattern => $label) {
            if (preg_match($pattern, mb_strtolower($text))) {
                $role = $label;
                break;
            }
        }
        $zone = 'Torino e provincia';
        if (preg_match('/\\b(torino|moncalieri|rivoli|collegno|settimo(?:\\s+torinese)?|chieri|lingotto|mirafiori|san\\s+donato|cit\\s+turin)\\b/iu', $text, $match)
            || preg_match('/(?:via|viale|piazza|corso|strada|localit[aà])\\s+[^,\\n]{2,60},?\\s*([^\\n,]{2,40}(?:\\s*\\([A-Z]{2}\\))?)/iu', $text, $match)) {
            $zone = mb_convert_case(trim($match[1]), MB_CASE_TITLE, 'UTF-8');
        }
        $shift = 'Da concordare';
        if (preg_match('/\\b(serale|notturn[oa]|diurno|part[ -]?time|full[ -]?time|weekend|sabato|domenica)\\b/iu', $text, $match)) {
            $shift = mb_convert_case($match[1], MB_CASE_TITLE, 'UTF-8');
        }
        if (preg_match('/\\b(?:dalle?|ore)\\s*(\\d{1,2}(?::\\d{2})?)\\s*(?:alle?|[-–])\\s*(\\d{1,2}(?::\\d{2})?)/iu', $text, $hours)) {
            $shift .= ($shift === 'Da concordare' ? '' : ' · ') . 'Dalle ' . $hours[1] . ' alle ' . $hours[2];
        }
        $salary = preg_match('/(?:€\\s*\\d{1,4}(?:[.,]\\d{1,2})?|\\d{1,4}(?:[.,]\\d{1,2})?\\s*(?:€|euro))/iu', $text, $match)
            ? trim($match[0]) : '';
        $username = trim((string) ($user['username'] ?? ''));
        $contact = $username !== '' ? '@' . $username : 'Profilo Telegram verificato';
        if (preg_match('/(?:contatt[oi]|tel(?:efono)?|whatsapp|wa)\\s*[:\\-]?\\s*([^\\n:]{0,35})?\\s*[:\\-]?\\s*(\\+?39[ .-]?)?(\\d(?:[ .-]?\\d){8,10})/iu', $text, $phone)) {
            $name = trim((string) ($phone[1] ?? ''));
            $number = trim((string) (($phone[2] ?? '') . ($phone[3] ?? '')));
            $contact = ($name !== '' ? $name . ': ' : '') . $number;
        }
        return [
            'business_name' => 'Locale non specificato', 'role' => $role, 'zone' => $zone,
            'shift' => $shift, 'salary' => $salary,
            'description' => mb_substr(trim($text), 0, 1000),
            'contact' => $contact,
        ];
    }

    /** @param array<string,string> $fields @param array<string,mixed> $user */
    private function automaticOfferText(array $fields, array $user): string
    {
        $username = trim((string) ($user['username'] ?? ''));
        $identity = $username !== '' ? '@' . self::html($username) : 'Profilo Telegram verificato';
        return "✅ <b>OFFERTA ORGANIZZATA AUTOMATICAMENTE DAL BOT</b>\n"
            . '🏪 <b>' . self::html(mb_strtoupper($fields['business_name'])) . "</b>\n\n"
            . '💼 <b>Ruolo cercato:</b> ' . self::html($fields['role']) . "\n"
            . '📍 <b>Zona:</b> ' . self::html($fields['zone']) . "\n"
            . '⏰ <b>Turni:</b> ' . self::html($fields['shift']) . "\n"
            . '💰 <b>Paga:</b> ' . self::html($fields['salary'] ?: 'Da concordare') . "\n\n"
            . '📝 <b>Descrizione e requisiti:</b>\n' . self::html($fields['description']) . "\n\n"
            . '📞 <b>Contatto:</b> ' . self::html($fields['contact']) . "\n"
            . '👤 <b>Pubblicato da:</b> <a href="tg://user?id=' . (int) $user['id'] . '">' . $identity . "</a>\n\n"
            . '🎯 Matching attivo · ⚡ Candidatura rapida in 1-click';
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
        if ($action !== 'publish_job_offer') {
            return;
        }
        if (!$this->contactBelongsToAuthor((string) ($data['contact'] ?? ''), $user)) {
            $this->telegram->call('sendMessage', [
                'chat_id' => $chatId,
                'text' => '🛡 Il contatto Telegram non coincide con l’account che sta pubblicando.',
            ]);
            return;
        }
        $package = (string) ($data['package'] ?? 'free');
        if ($package !== 'free') {
            $plan = HorecaRepository::paidPackage($package);
            if (!$plan) return;
            $jobId = $repository->createPaidJob($user, $data, $package);
            $this->telegram->call('sendInvoice', [
                'chat_id'=>$chatId,
                'title'=>'Promozione annuncio Horeca',
                'description'=>$plan['label'] . ': maggiore visibilità, pin e notifiche rapide ai candidati Premium.',
                'payload'=>'job_offer_id_' . $jobId,
                'provider_token'=>'','currency'=>'XTR',
                'prices'=>[['label'=>$plan['label'],'amount'=>$plan['amount']]],
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

    /** @param array<string,mixed> $data @param array<string,mixed> $user */
    private function offerMessage(array $data, array $user, bool $paid): string
    {
        $username = trim((string) ($user['username'] ?? $data['username'] ?? ''));
        $identity = $username !== '' ? '@' . self::html($username) : 'Profilo Telegram verificato';
        $header = $paid ? '🌟 <b>OFFERTA SPONSOR VERIFICATA</b>' : '✅ <b>OFFERTA ORGANIZZATA CON IL BOT</b>';
        return $header . "\n" . '🏪 <b>' . self::html(mb_strtoupper((string) $data['business_name'])) . "</b>\n\n"
            . '💼 <b>Ruolo:</b> ' . self::html($data['role'] ?? '') . "\n"
            . '📍 <b>Zona:</b> ' . self::html($data['zone'] ?? '') . "\n"
            . '⏰ <b>Turni:</b> ' . self::html($data['shift'] ?? '') . "\n"
            . '💰 <b>Paga:</b> ' . self::html(($data['salary'] ?? '') ?: 'Trattabile') . "\n\n"
            . '📝 ' . self::html($data['description'] ?? '') . "\n\n"
            . '📞 <b>Contatto:</b> ' . self::html($data['contact'] ?? '') . "\n"
            . '👤 <b>Pubblicato da:</b> <a href="tg://user?id=' . (int) $user['id'] . '">' . $identity . '</a>';
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
        if ($data === 'pay_stars') {
            if (!$repository->candidateProfile($candidateId)) {
                $this->telegram->call('sendMessage', ['chat_id' => $chatId, 'text' => 'Crea prima il profilo candidato con /registrati.']);
                return;
            }
            $this->telegram->call('sendInvoice', [
                'chat_id' => $chatId,
                'title' => 'Candidato Premium Horeca (30 giorni)',
                'description' => 'Notifiche immediate e profilo prioritario per 30 giorni.',
                'payload' => 'premium_subscription_stars',
                'provider_token' => '',
                'currency' => 'XTR',
                'prices' => [['label' => 'Premium 30 giorni', 'amount' => 100]],
            ]);
            return;
        }
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
