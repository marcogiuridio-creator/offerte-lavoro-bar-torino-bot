<?php
declare(strict_types=1);

use Horeca\Bootstrap;
use Horeca\CronRunner;
use Horeca\Http;
use Horeca\TelegramClient;

require dirname(__DIR__).'/src/Bootstrap.php';
require dirname(__DIR__).'/src/Http.php';
require dirname(__DIR__).'/src/TelegramClient.php';
require dirname(__DIR__).'/src/HorecaRepository.php';
require dirname(__DIR__).'/src/CronRunner.php';

try {
    $config=Bootstrap::config(); $expected=(string)($config['telegram']['webhook_secret']??'');
    $provided=(string)($_SERVER['HTTP_X_HORECA_CRON_SECRET']??($_GET['key']??''));
    if ($expected==='' || !hash_equals($expected,$provided)) Http::json(401,['status'=>'error','error'=>'unauthorized']);
    Http::json(200,['status'=>'ok','result'=>(new CronRunner(Bootstrap::db(),new TelegramClient((string)$config['telegram']['bot_token']),$config))->run()]);
} catch (Throwable $error) { error_log('horeca cron error: '.$error->getMessage()); Http::json(500,['status'=>'error','error'=>'internal_error']); }
