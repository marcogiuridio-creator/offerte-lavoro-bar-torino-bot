<?php
declare(strict_types=1);

namespace Horeca;

use RuntimeException;

final class TelegramClient
{
    public function __construct(private readonly string $token)
    {
        if (!preg_match('/^[0-9]+:[A-Za-z0-9_-]+$/', $token)) {
            throw new RuntimeException('Token Telegram mancante.');
        }
    }

    /** @param array<string,mixed> $parameters
     *  @return array<string,mixed>
     */
    public function call(string $method, array $parameters = []): array
    {
        $url = 'https://api.telegram.org/bot' . $this->token . '/' . rawurlencode($method);
        $body = json_encode($parameters, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        if (function_exists('curl_init')) {
            $curl = curl_init($url);
            curl_setopt_array($curl, [
                CURLOPT_POST => true, CURLOPT_POSTFIELDS => $body, CURLOPT_RETURNTRANSFER => true,
                CURLOPT_HTTPHEADER => ['Content-Type: application/json'], CURLOPT_TIMEOUT => 12,
            ]);
            $response = curl_exec($curl);
            curl_close($curl);
        } else {
            $context = stream_context_create(['http' => [
                'method' => 'POST', 'header' => "Content-Type: application/json\r\n",
                'content' => $body, 'timeout' => 12, 'ignore_errors' => true,
            ]]);
            $response = @file_get_contents($url, false, $context);
        }
        $decoded = is_string($response) ? json_decode($response, true) : null;
        if (!is_array($decoded) || !($decoded['ok'] ?? false)) {
            throw new RuntimeException('Chiamata Telegram non riuscita: ' . $method);
        }
        return $decoded;
    }
}
