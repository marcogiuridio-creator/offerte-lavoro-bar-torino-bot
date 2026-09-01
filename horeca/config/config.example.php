<?php
declare(strict_types=1);

// Copiare come config/local.php direttamente su Aruba. Non versionare local.php.
return [
    'app' => [
        'base_url' => 'https://www.raiseyourbar.it/horeca',
        'timezone' => 'Europe/Rome',
        'environment' => 'staging',
    ],
    'telegram' => [
        'bot_token' => 'INSERIRE_SU_ARUBA',
        'bot_username' => 'lavorotorinobot',
        'webhook_secret' => 'GENERARE_UN_VALORE_CASUALE',
        'group_id' => 0,
        'admin_ids' => [21773014],
    ],
    'database' => [
        'host' => 'INSERIRE_HOST_MYSQL_ARUBA',
        'port' => 3306,
        'name' => 'INSERIRE_DATABASE',
        'username' => 'INSERIRE_USERNAME',
        'password' => 'INSERIRE_SU_ARUBA',
        'charset' => 'utf8mb4',
    ],
    'limits' => [
        'rate_hours' => 6,
        'daily_max' => 2,
        // I messaggi normali riconosciuti come offerte hanno limiti separati:
        // non devono restare in chat solo perché il datore ha già pubblicato da modulo.
        'automatic_rate_hours' => 0,
        'automatic_daily_max' => 10,
    ],
];
