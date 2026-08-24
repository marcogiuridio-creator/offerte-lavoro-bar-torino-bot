<?php
declare(strict_types=1);

use Horeca\Bootstrap;
use Horeca\Http;
use Horeca\TelegramClient;

require dirname(__DIR__).'/src/Bootstrap.php';
require dirname(__DIR__).'/src/Http.php';
require dirname(__DIR__).'/src/TelegramClient.php';

try {
    $config=Bootstrap::config();
    $expected=(string)($config['telegram']['webhook_secret']??'');
    $provided=(string)($_SERVER['HTTP_X_HORECA_OPS_SECRET']??'');
    if ($expected==='' || !hash_equals($expected,$provided)) Http::json(401,['status'=>'error','error'=>'unauthorized']);
    $body=json_decode((string)file_get_contents('php://input'),true,64,JSON_THROW_ON_ERROR);
    $action=(string)($body['action']??''); $db=Bootstrap::db();
    if ($action==='migrate_paid') {
        foreach (['promotion_expires_at'=>'DATETIME NULL AFTER message_id','last_bumped_at'=>'DATETIME NULL AFTER promotion_expires_at'] as $column=>$definition) {
            $check=$db->prepare('SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=\'job_offers\' AND COLUMN_NAME=:column');
            $check->execute(['column'=>$column]);
            if ((int)$check->fetchColumn()===0) $db->exec("ALTER TABLE job_offers ADD COLUMN {$column} {$definition}");
        }
        Http::json(200,['status'=>'ok','migration'=>'paid_promotions']);
    }
    $telegram=new TelegramClient((string)$config['telegram']['bot_token']);
    if ($action==='webhook_info') Http::json(200,['status'=>'ok','telegram'=>$telegram->call('getWebhookInfo')]);
    if ($action==='set_webhook') {
        $url=rtrim((string)$config['app']['base_url'],'/').'/api/telegram-webhook.php';
        Http::json(200,['status'=>'ok','telegram'=>$telegram->call('setWebhook',['url'=>$url,'secret_token'=>$expected,'drop_pending_updates'=>false])]);
    }
    Http::json(400,['status'=>'error','error'=>'unknown_action']);
} catch (Throwable $error) { error_log('horeca ops error: '.$error->getMessage()); Http::json(500,['status'=>'error','error'=>'internal_error']); }
