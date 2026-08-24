<?php
declare(strict_types=1);

namespace Horeca;

use PDO;

final class CronRunner
{
    public function __construct(private readonly PDO $db, private readonly TelegramClient $telegram, private readonly array $config) {}

    /** @return array{expired:int,bumped:int,daily:int} */
    public function run(): array
    {
        if ((int) $this->db->query("SELECT GET_LOCK('horeca_cron',0)")->fetchColumn() !== 1) return ['expired'=>0,'bumped'=>0,'daily'=>0];
        try {
            $repo=new HorecaRepository($this->db); $group=(int) ($this->config['telegram']['group_id'] ?? 0);
            $expired=$bumped=$daily=0;
            foreach ($repo->expiredPromotions() as $job) {
                if (!empty($job['message_id'])) try { $this->telegram->call('unpinChatMessage',['chat_id'=>$group,'message_id'=>(int)$job['message_id']]); } catch (\Throwable) {}
                $repo->markPromotionEnded((int)$job['job_id']); $expired++;
            }
            foreach ($repo->dueVipBumps() as $job) {
                if (!empty($job['message_id'])) try { $this->telegram->call('unpinChatMessage',['chat_id'=>$group,'message_id'=>(int)$job['message_id']]); } catch (\Throwable) {}
                $sent=$this->telegram->call('sendMessage',['chat_id'=>$group,'text'=>$this->jobText($job),'parse_mode'=>'HTML',
                    'reply_markup'=>['inline_keyboard'=>[[['text'=>'📩 Candidati in 1-Click','callback_data'=>'apply_start:'.(int)$job['job_id']]]]]]);
                $messageId=(int)($sent['result']['message_id']??0);
                $this->telegram->call('pinChatMessage',['chat_id'=>$group,'message_id'=>$messageId,'disable_notification'=>true]);
                $repo->markBumped((int)$job['job_id'],$messageId); $bumped++;
            }
            $rome=new \DateTimeImmutable('now',new \DateTimeZone('Europe/Rome')); $today=$rome->format('Y-m-d');
            if ((int)$rome->format('H')>=11 && $repo->setting('daily_rules_date')!==$today) {
                $previous=(int)($repo->setting('daily_rules_message_id')??0);
                if ($previous) try { $this->telegram->call('deleteMessage',['chat_id'=>$group,'message_id'=>$previous]); } catch (\Throwable) {}
                $sent=$this->telegram->call('sendMessage',['chat_id'=>$group,'text'=>$this->rules(),'parse_mode'=>'HTML','disable_notification'=>true]);
                $id=(int)($sent['result']['message_id']??0); $this->telegram->call('pinChatMessage',['chat_id'=>$group,'message_id'=>$id,'disable_notification'=>true]);
                $repo->setSetting('daily_rules_message_id',(string)$id); $repo->setSetting('daily_rules_date',$today); $daily=1;
            }
            return compact('expired','bumped','daily');
        } finally { $this->db->query("SELECT RELEASE_LOCK('horeca_cron')"); }
    }

    /** @param array<string,mixed> $j */
    private function jobText(array $j): string { return '🌟 <b>OFFERTA VIP</b>' . "\n🏪 <b>" . self::h($j['business_name']) . "</b>\n\n💼 " . self::h($j['role']) . "\n📍 " . self::h($j['zone']) . "\n⏰ " . self::h($j['shift']) . "\n💰 " . self::h($j['salary'] ?: 'Trattabile') . "\n\n📝 " . self::h($j['description']); }
    private function rules(): string { return "📌 <b>IL BOT ORGANIZZA AUTOMATICAMENTE LE OFFERTE</b>\n\n🏪 Scrivi normalmente il tuo annuncio: il bot lo trasforma gratis in un’offerta chiara.\n\n✅ più visibilità\n⚡ candidature in 1-click\n📊 dashboard candidati\n👤 matching con profili compatibili\n\nCerchi lavoro? Registrati gratis con /registrati. Premium: /premium\nRegole: /regole"; }
    private static function h(mixed $v): string { return htmlspecialchars(trim((string)$v),ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8'); }
}
