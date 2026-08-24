<?php
declare(strict_types=1);

namespace Horeca;

final class TelegramAuth
{
    /** @return array<string,mixed>|null */
    public static function validate(string $initData, string $botToken, int $maxAge = 900, ?int $now = null): ?array
    {
        if ($initData === '' || $botToken === '') {
            return null;
        }
        parse_str($initData, $values);
        $suppliedHash = (string) ($values['hash'] ?? '');
        if ($suppliedHash === '') {
            return null;
        }
        unset($values['hash']);
        ksort($values, SORT_STRING);
        $parts = [];
        foreach ($values as $key => $value) {
            $parts[] = $key . '=' . $value;
        }
        $secret = hash_hmac('sha256', $botToken, 'WebAppData', true);
        $expected = hash_hmac('sha256', implode("\n", $parts), $secret);
        if (!hash_equals($expected, $suppliedHash)) {
            return null;
        }
        $authDate = filter_var($values['auth_date'] ?? null, FILTER_VALIDATE_INT);
        $clock = $now ?? time();
        if ($authDate === false || abs($clock - $authDate) > $maxAge) {
            return null;
        }
        $user = json_decode((string) ($values['user'] ?? ''), true);
        if (!is_array($user) || !isset($user['id']) || !is_numeric($user['id'])) {
            return null;
        }
        $user['id'] = (int) $user['id'];
        return $user;
    }
}

