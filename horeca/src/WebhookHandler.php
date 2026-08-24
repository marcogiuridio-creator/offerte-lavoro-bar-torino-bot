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
        }
    }
}

