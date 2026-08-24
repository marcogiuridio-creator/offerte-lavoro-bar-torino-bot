<?php
declare(strict_types=1);

namespace Horeca;

use RuntimeException;

final class TelegramClient
{
    public function __construct(private readonly string $token)
    {
        if ($token === '') {
            throw new RuntimeException('Token Telegram mancante.');
        }
    }

    /** @param array<string,mixed> $parameters
     *  @return array<string,mixed>
     */
    public function call(string $method, array $parameters = []): array
    {
        $url = 'https://api.telegram.org/bot' . rawurlencode($this->token) . '/' . $method;
        $body = json_encode($parameters, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $context = stream_context_create(['http' => [
            'method' => 'POST',
            'header' => "Content-Type: application/json\r\n",
            'content' => $body,
            'timeout' => 12,
            'ignore_errors' => true,
        ]]);
        $response = @file_get_contents($url, false, $context);
        $decoded = is_string($response) ? json_decode($response, true) : null;
        if (!is_array($decoded) || !($decoded['ok'] ?? false)) {
            throw new RuntimeException('Chiamata Telegram non riuscita: ' . $method);
        }
        return $decoded;
    }
}

