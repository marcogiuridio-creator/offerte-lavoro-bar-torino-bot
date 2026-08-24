<?php
declare(strict_types=1);

namespace Horeca;

use PDO;

final class HorecaRepository
{
    public function __construct(private readonly PDO $db) {}

    /** @param array<string,mixed> $user @param array<string,mixed> $profile */
    public function saveCandidateProfile(array $user, array $profile): void
    {
        $this->db->beginTransaction();
        try {
            $userSql = 'INSERT INTO users (user_id, username, first_name, last_name, role)
                VALUES (:id, :username, :first_name, :last_name, \'lavoratore\')
                ON DUPLICATE KEY UPDATE username=VALUES(username), first_name=VALUES(first_name),
                    last_name=VALUES(last_name), role=\'lavoratore\'';
            $this->db->prepare($userSql)->execute([
                'id' => $user['id'],
                'username' => $user['username'] ?? '',
                'first_name' => $user['first_name'] ?? '',
                'last_name' => $user['last_name'] ?? '',
            ]);
            $sql = 'INSERT INTO candidate_profiles
                (user_id, username, first_name, roles, skills, experience, availability, zones, phone, bio)
                VALUES (:user_id,:username,:first_name,:roles,:skills,:experience,:availability,:zones,:phone,:bio)
                ON DUPLICATE KEY UPDATE username=VALUES(username), first_name=VALUES(first_name),
                    roles=VALUES(roles), skills=VALUES(skills), experience=VALUES(experience),
                    availability=VALUES(availability), zones=VALUES(zones), phone=VALUES(phone),
                    bio=VALUES(bio), updated_at=UTC_TIMESTAMP()';
            $this->db->prepare($sql)->execute([
                'user_id' => $user['id'],
                'username' => $user['username'] ?? '',
                'first_name' => $user['first_name'] ?? '',
                'roles' => self::jsonArray($profile['roles'] ?? []),
                'skills' => self::jsonArray($profile['skills'] ?? []),
                'experience' => self::limited($profile['experience'] ?? '', 4000),
                'availability' => self::jsonArray($profile['availability'] ?? []),
                'zones' => self::jsonArray($profile['zones'] ?? []),
                'phone' => self::limited($profile['phone'] ?? '', 64),
                'bio' => self::limited($profile['bio'] ?? '', 4000),
            ]);
            $this->db->commit();
        } catch (\Throwable $error) {
            $this->db->rollBack();
            throw $error;
        }
    }

    /** @return array<string,mixed>|null */
    public function candidateProfile(int $userId): ?array
    {
        $statement = $this->db->prepare('SELECT * FROM candidate_profiles WHERE user_id=:id');
        $statement->execute(['id' => $userId]);
        $row = $statement->fetch();
        return is_array($row) ? $row : null;
    }

    /** @return array<string,mixed>|null */
    public function job(int $jobId): ?array
    {
        $statement = $this->db->prepare('SELECT * FROM job_offers WHERE job_id=:id');
        $statement->execute(['id' => $jobId]);
        $row = $statement->fetch();
        return is_array($row) ? $row : null;
    }

    /** @return list<array<string,mixed>> */
    public function userOffers(int $userId): array
    {
        $statement = $this->db->prepare(
            'SELECT * FROM job_offers WHERE user_id=:user_id ORDER BY created_at DESC LIMIT 20'
        );
        $statement->execute(['user_id' => $userId]);
        return $statement->fetchAll();
    }

    /** @return array{users:int,offers:int,candidates:int,applications:int} */
    public function totals(): array
    {
        return [
            'users' => (int) $this->db->query('SELECT COUNT(*) FROM users')->fetchColumn(),
            'offers' => (int) $this->db->query('SELECT COUNT(*) FROM job_offers')->fetchColumn(),
            'candidates' => (int) $this->db->query('SELECT COUNT(*) FROM candidate_profiles')->fetchColumn(),
            'applications' => (int) $this->db->query('SELECT COUNT(*) FROM applications')->fetchColumn(),
        ];
    }

    public function activatePremiumPayment(
        int $userId,
        string $transactionId,
        string $payload,
        string $currency,
        int $amount
    ): ?string {
        if ($transactionId === '' || $payload !== 'premium_subscription_stars'
            || $currency !== 'XTR' || $amount !== 100 || !$this->candidateProfile($userId)) {
            return null;
        }
        $this->db->beginTransaction();
        try {
            $payment = $this->db->prepare('INSERT IGNORE INTO payment_events
                (transaction_id,user_id,payload,currency,amount) VALUES (:transaction_id,:user_id,:payload,:currency,:amount)');
            $payment->execute([
                'transaction_id' => $transactionId, 'user_id' => $userId, 'payload' => $payload,
                'currency' => $currency, 'amount' => $amount,
            ]);
            if ($payment->rowCount() !== 1) {
                $this->db->rollBack();
                return null;
            }
            $statement = $this->db->prepare('UPDATE candidate_profiles SET is_premium=1,
                premium_until=DATE_ADD(GREATEST(COALESCE(premium_until,UTC_TIMESTAMP()),UTC_TIMESTAMP()), INTERVAL 30 DAY)
                WHERE user_id=:user_id');
            $statement->execute(['user_id' => $userId]);
            $expiry = $this->db->prepare('SELECT premium_until FROM candidate_profiles WHERE user_id=:user_id');
            $expiry->execute(['user_id' => $userId]);
            $value = $expiry->fetchColumn();
            $this->db->commit();
            return is_string($value) ? $value : null;
        } catch (\Throwable $error) {
            $this->db->rollBack();
            throw $error;
        }
    }

    /** @return list<array<string,mixed>> */
    public function employerCandidates(int $jobId, int $employerId, bool $isAdmin): array
    {
        $job = $this->job($jobId);
        if (!$job || (!$isAdmin && (int) $job['user_id'] !== $employerId)) {
            return [];
        }
        $sql = 'SELECT a.app_id,a.candidate_id,a.candidate_user,a.match_score,a.screening_q1,
                a.screening_q2,a.status AS application_status,c.first_name,c.username,c.phone,c.experience,c.roles,c.skills,c.is_premium
            FROM applications a JOIN candidate_profiles c ON c.user_id=a.candidate_id
            WHERE a.job_id=:job_id ORDER BY c.is_premium DESC,a.match_score DESC,a.created_at ASC';
        $statement = $this->db->prepare($sql);
        $statement->execute(['job_id' => $jobId]);
        return $statement->fetchAll();
    }

    /** @param array<string,mixed> $fields */
    public function updateJob(int $jobId, int $ownerId, bool $isAdmin, array $fields): bool
    {
        $job = $this->job($jobId);
        if (!$job || (!$isAdmin && (int) $job['user_id'] !== $ownerId)) {
            return false;
        }
        $sql = 'UPDATE job_offers SET business_name=:business_name,role=:role,zone=:zone,
            shift=:shift,salary=:salary,description=:description WHERE job_id=:job_id';
        $this->db->prepare($sql)->execute([
            'business_name' => self::limited($fields['business_name'] ?? '', 255),
            'role' => self::limited($fields['role'] ?? '', 255),
            'zone' => self::limited($fields['zone'] ?? '', 255),
            'shift' => self::limited($fields['shift'] ?? '', 255),
            'salary' => self::limited($fields['salary'] ?? '', 255),
            'description' => self::limited($fields['description'] ?? '', 10000),
            'job_id' => $jobId,
        ]);
        return true;
    }

    public function updateApplicationStatus(int $appId, int $ownerId, string $status): bool
    {
        if (!in_array($status, ['interview', 'rejected', 'hired'], true)) {
            return false;
        }
        $sql = 'UPDATE applications a JOIN job_offers j ON j.job_id=a.job_id
            SET a.status=:status WHERE a.app_id=:app_id AND j.user_id=:owner_id';
        $statement = $this->db->prepare($sql);
        $statement->execute(['status' => $status, 'app_id' => $appId, 'owner_id' => $ownerId]);
        return $statement->rowCount() === 1;
    }

    /** @param array<string,mixed> $user @param array<string,mixed> $fields */
    public function createFreeJob(array $user, array $fields, int $hours, int $dailyMax): array
    {
        $this->db->beginTransaction();
        try {
            $this->db->prepare('INSERT INTO users (user_id,username,first_name,last_name,role)
                VALUES (:id,:username,:first_name,:last_name,\'datore\')
                ON DUPLICATE KEY UPDATE username=VALUES(username),first_name=VALUES(first_name),
                    last_name=VALUES(last_name),role=\'datore\'')->execute([
                'id' => $user['id'], 'username' => $user['username'] ?? '',
                'first_name' => $user['first_name'] ?? '', 'last_name' => $user['last_name'] ?? '',
            ]);
            $lock = $this->db->prepare('SELECT last_post,posts_today,last_date FROM users WHERE user_id=:id FOR UPDATE');
            $lock->execute(['id' => $user['id']]);
            $quota = $lock->fetch();
            $today = (new \DateTimeImmutable('now'))->format('Y-m-d');
            $count = (($quota['last_date'] ?? null) === $today) ? (int) ($quota['posts_today'] ?? 0) : 0;
            if ($count >= $dailyMax) {
                $this->db->rollBack();
                return ['ok' => false, 'error' => "Hai già pubblicato {$dailyMax} annunci oggi."];
            }
            if (!empty($quota['last_post'])) {
                $next = (new \DateTimeImmutable((string) $quota['last_post']))->modify("+{$hours} hours");
                if ($next > new \DateTimeImmutable('now')) {
                    $this->db->rollBack();
                    return ['ok' => false, 'error' => 'Prossima pubblicazione alle ' . $next->format('H:i') . '.'];
                }
            }
            $this->db->prepare('UPDATE users SET last_post=UTC_TIMESTAMP(),posts_today=:count,last_date=:today,
                offerte_count=offerte_count+1 WHERE user_id=:id')->execute([
                'count' => $count + 1, 'today' => $today, 'id' => $user['id'],
            ]);
            $sql = 'INSERT INTO job_offers
                (user_id,username,business_name,role,zone,shift,salary,description,contact,package,is_verified)
                VALUES (:user_id,:username,:business_name,:role,:zone,:shift,:salary,:description,:contact,\'free\',0)';
            $this->db->prepare($sql)->execute([
                'user_id' => $user['id'], 'username' => $user['username'] ?? '',
                'business_name' => self::required($fields['business_name'] ?? '', 255, 'locale'),
                'role' => self::required($fields['role'] ?? '', 255, 'ruolo'),
                'zone' => self::required($fields['zone'] ?? '', 255, 'zona'),
                'shift' => self::limited($fields['shift'] ?? '', 255),
                'salary' => self::limited($fields['salary'] ?? '', 255),
                'description' => self::limited($fields['description'] ?? '', 10000),
                'contact' => self::required($fields['contact'] ?? '', 255, 'contatto'),
            ]);
            $jobId = (int) $this->db->lastInsertId();
            $this->db->commit();
            return ['ok' => true, 'job_id' => $jobId];
        } catch (\Throwable $error) {
            if ($this->db->inTransaction()) {
                $this->db->rollBack();
            }
            throw $error;
        }
    }

    public function attachMessage(int $jobId, int $messageId): void
    {
        $this->db->prepare('UPDATE job_offers SET message_id=:message_id WHERE job_id=:job_id')
            ->execute(['message_id' => $messageId, 'job_id' => $jobId]);
    }

    /** @param array<string,mixed> $user @param array<string,mixed> $fields */
    public function createPaidJob(array $user, array $fields, string $package): int
    {
        if (!isset(self::paidPackages()[$package])) {
            throw new \InvalidArgumentException('Pacchetto promozionale non valido.');
        }
        $this->db->beginTransaction();
        try {
            $this->db->prepare('INSERT INTO users (user_id,username,first_name,last_name,role)
                VALUES (:id,:username,:first_name,:last_name,\'datore\')
                ON DUPLICATE KEY UPDATE username=VALUES(username),first_name=VALUES(first_name),
                    last_name=VALUES(last_name),role=\'datore\'')->execute([
                'id' => $user['id'], 'username' => $user['username'] ?? '',
                'first_name' => $user['first_name'] ?? '', 'last_name' => $user['last_name'] ?? '',
            ]);
            $sql = 'INSERT INTO job_offers
                (user_id,username,business_name,role,zone,shift,salary,description,contact,package,is_verified)
                VALUES (:user_id,:username,:business_name,:role,:zone,:shift,:salary,:description,:contact,:package,0)';
            $this->db->prepare($sql)->execute([
                'user_id' => $user['id'], 'username' => $user['username'] ?? '',
                'business_name' => self::required($fields['business_name'] ?? '', 255, 'locale'),
                'role' => self::required($fields['role'] ?? '', 255, 'ruolo'),
                'zone' => self::required($fields['zone'] ?? '', 255, 'zona'),
                'shift' => self::limited($fields['shift'] ?? '', 255),
                'salary' => self::limited($fields['salary'] ?? '', 255),
                'description' => self::limited($fields['description'] ?? '', 10000),
                'contact' => self::required($fields['contact'] ?? '', 255, 'contatto'),
                'package' => $package,
            ]);
            $jobId = (int) $this->db->lastInsertId();
            $this->db->commit();
            return $jobId;
        } catch (\Throwable $error) {
            if ($this->db->inTransaction()) $this->db->rollBack();
            throw $error;
        }
    }

    /** @return array{amount:int,days:int,label:string}|null */
    public static function paidPackage(string $package): ?array
    {
        return self::paidPackages()[$package] ?? null;
    }

    public function validJobCheckout(int $userId, string $payload, string $currency, int $amount): bool
    {
        if (!preg_match('/^job_offer_id_(\d+)$/', $payload, $match) || $currency !== 'XTR') return false;
        $job = $this->job((int) $match[1]);
        $plan = $job ? self::paidPackage((string) $job['package']) : null;
        return $job && $plan && (int) $job['user_id'] === $userId && !(int) $job['is_verified']
            && $amount === $plan['amount'];
    }

    /** @return array<string,mixed>|null */
    public function activatePaidJobPayment(int $userId, string $transactionId, string $payload, string $currency, int $amount): ?array
    {
        if ($transactionId === '' || !preg_match('/^job_offer_id_(\d+)$/', $payload, $match)) return null;
        $jobId = (int) $match[1];
        $this->db->beginTransaction();
        try {
            $lock = $this->db->prepare('SELECT * FROM job_offers WHERE job_id=:id FOR UPDATE');
            $lock->execute(['id' => $jobId]);
            $job = $lock->fetch();
            $plan = is_array($job) ? self::paidPackage((string) $job['package']) : null;
            if (!$job || !$plan || (int) $job['user_id'] !== $userId || (int) $job['is_verified'] !== 0
                || $currency !== 'XTR' || $amount !== $plan['amount']) {
                $this->db->rollBack(); return null;
            }
            $payment = $this->db->prepare('INSERT IGNORE INTO payment_events
                (transaction_id,user_id,payload,currency,amount) VALUES (:transaction_id,:user_id,:payload,:currency,:amount)');
            $payment->execute(['transaction_id'=>$transactionId,'user_id'=>$userId,'payload'=>$payload,'currency'=>$currency,'amount'=>$amount]);
            if ($payment->rowCount() !== 1) { $this->db->rollBack(); return null; }
            $sql = 'UPDATE job_offers SET is_verified=1,promotion_expires_at=DATE_ADD(UTC_TIMESTAMP(), INTERVAL '
                . (int) $plan['days'] . ' DAY),last_bumped_at=UTC_TIMESTAMP() WHERE job_id=:id';
            $this->db->prepare($sql)->execute(['id' => $jobId]);
            $this->db->commit();
            return $this->job($jobId);
        } catch (\Throwable $error) {
            if ($this->db->inTransaction()) $this->db->rollBack();
            throw $error;
        }
    }

    /** @return list<array<string,mixed>> */
    public function activePremiumCandidates(): array
    {
        return $this->db->query('SELECT user_id,roles,zones FROM candidate_profiles
            WHERE is_premium=1 AND premium_until>UTC_TIMESTAMP()')->fetchAll();
    }

    /** @return list<array<string,mixed>> */
    public function expiredPromotions(): array
    {
        return $this->db->query("SELECT * FROM job_offers WHERE is_verified=1
            AND package IN ('evidenza','vip','vip_mensile') AND promotion_ended_at IS NULL
            AND promotion_expires_at IS NOT NULL AND promotion_expires_at<=UTC_TIMESTAMP() LIMIT 50")->fetchAll();
    }

    /** @return list<array<string,mixed>> */
    public function dueVipBumps(): array
    {
        return $this->db->query("SELECT * FROM job_offers WHERE is_verified=1
            AND package IN ('vip','vip_mensile') AND promotion_ended_at IS NULL
            AND promotion_expires_at>UTC_TIMESTAMP()
            AND (last_bumped_at IS NULL OR last_bumped_at<=DATE_SUB(UTC_TIMESTAMP(),INTERVAL 3 HOUR)) LIMIT 20")->fetchAll();
    }

    public function markPromotionEnded(int $jobId): void
    {
        $this->db->prepare('UPDATE job_offers SET promotion_ended_at=UTC_TIMESTAMP() WHERE job_id=:id AND promotion_ended_at IS NULL')
            ->execute(['id'=>$jobId]);
    }

    public function markBumped(int $jobId, int $messageId): void
    {
        $this->db->prepare('UPDATE job_offers SET message_id=:message_id,last_bumped_at=UTC_TIMESTAMP() WHERE job_id=:id')
            ->execute(['id'=>$jobId,'message_id'=>$messageId]);
    }

    public function setting(string $key): ?string
    {
        $statement=$this->db->prepare('SELECT value FROM bot_settings WHERE `key`=:key');
        $statement->execute(['key'=>$key]); $value=$statement->fetchColumn();
        return is_string($value) ? $value : null;
    }

    public function setSetting(string $key, string $value): void
    {
        $this->db->prepare('INSERT INTO bot_settings (`key`,value) VALUES (:key,:value)
            ON DUPLICATE KEY UPDATE value=VALUES(value)')->execute(['key'=>$key,'value'=>$value]);
    }

    /** @return array<string,array{amount:int,days:int,label:string}> */
    private static function paidPackages(): array
    {
        return [
            'evidenza' => ['amount'=>250,'days'=>1,'label'=>'In evidenza 24 ore'],
            'vip' => ['amount'=>500,'days'=>7,'label'=>'VIP 7 giorni'],
            'vip_mensile' => ['amount'=>1400,'days'=>30,'label'=>'VIP 30 giorni'],
        ];
    }

    /** @param array<string,mixed> $user */
    public function recordAutomaticConversion(
        array $user,
        int|string $chatId,
        int $originalMessageId,
        int $publishedMessageId,
        int $jobId,
        string $text
    ): void {
        $this->db->beginTransaction();
        try {
            $post = 'INSERT INTO posts (user_id,message_id,category,text,converted_job_id)
                VALUES (:user_id,:message_id,\'OFFERTA\',:text,:job_id)
                ON DUPLICATE KEY UPDATE category=\'OFFERTA\',text=VALUES(text),converted_job_id=VALUES(converted_job_id)';
            $this->db->prepare($post)->execute([
                'user_id' => $user['id'], 'message_id' => $originalMessageId,
                'text' => self::limited($text, 10000), 'job_id' => $jobId,
            ]);
            $event = 'INSERT INTO security_events
                (event_type,user_id,username,chat_id,message_id,visible_text,target,details)
                VALUES (\'manual_offer_auto_converted\',:user_id,:username,:chat_id,:message_id,
                    :visible_text,:target,:details)';
            $this->db->prepare($event)->execute([
                'user_id' => $user['id'], 'username' => $user['username'] ?? '',
                'chat_id' => $chatId, 'message_id' => $publishedMessageId,
                'visible_text' => $user['username'] ?? '',
                'target' => 'tg://user?id=' . (int) $user['id'],
                'details' => "Offerta manuale convertita automaticamente nell'offerta #{$jobId}.",
            ]);
            $this->db->commit();
        } catch (\Throwable $error) {
            $this->db->rollBack();
            throw $error;
        }
    }

    public function rollbackFreeJob(int $jobId, int $userId): void
    {
        $this->db->beginTransaction();
        try {
            $this->db->prepare('DELETE FROM job_offers WHERE job_id=:job_id AND user_id=:user_id AND message_id IS NULL')
                ->execute(['job_id' => $jobId, 'user_id' => $userId]);
            $this->db->prepare('UPDATE users SET posts_today=GREATEST(posts_today-1,0),
                offerte_count=GREATEST(offerte_count-1,0),last_post=NULL WHERE user_id=:user_id')
                ->execute(['user_id' => $userId]);
            $this->db->commit();
        } catch (\Throwable $error) {
            $this->db->rollBack();
            throw $error;
        }
    }

    public function saveScreeningAnswer(int $candidateId, int $jobId, string $field, string $answer): bool
    {
        if (!in_array($field, ['screening_q1', 'screening_q2'], true) || !$this->job($jobId)) {
            return false;
        }
        $sql = "INSERT INTO application_sessions (candidate_id,job_id,{$field}) VALUES (:candidate_id,:job_id,:answer)
            ON DUPLICATE KEY UPDATE {$field}=VALUES({$field}),updated_at=UTC_TIMESTAMP()";
        $this->db->prepare($sql)->execute([
            'candidate_id' => $candidateId, 'job_id' => $jobId, 'answer' => self::limited($answer, 255),
        ]);
        return true;
    }

    /** @return array<string,mixed>|null */
    public function screeningSession(int $candidateId, int $jobId): ?array
    {
        $statement = $this->db->prepare(
            'SELECT * FROM application_sessions WHERE candidate_id=:candidate_id AND job_id=:job_id'
        );
        $statement->execute(['candidate_id' => $candidateId, 'job_id' => $jobId]);
        $row = $statement->fetch();
        return is_array($row) ? $row : null;
    }

    public function submitApplication(int $candidateId, int $jobId, string $candidateUser): ?int
    {
        $session = $this->screeningSession($candidateId, $jobId);
        $profile = $this->candidateProfile($candidateId);
        if (!$session || !$profile || empty($session['screening_q1']) || empty($session['screening_q2'])) {
            return null;
        }
        $sql = 'INSERT INTO applications
            (job_id,candidate_id,candidate_user,match_score,screening_q1,screening_q2,screening_notes)
            VALUES (:job_id,:candidate_id,:candidate_user,:match_score,:q1,:q2,:notes)
            ON DUPLICATE KEY UPDATE screening_q1=VALUES(screening_q1),screening_q2=VALUES(screening_q2)';
        $this->db->prepare($sql)->execute([
            'job_id' => $jobId, 'candidate_id' => $candidateId, 'candidate_user' => $candidateUser,
            'match_score' => 50, 'q1' => $session['screening_q1'], 'q2' => $session['screening_q2'],
            'notes' => 'Candidatura inviata tramite pre-screening Aruba',
        ]);
        $statement = $this->db->prepare('SELECT app_id FROM applications WHERE job_id=:job_id AND candidate_id=:candidate_id');
        $statement->execute(['job_id' => $jobId, 'candidate_id' => $candidateId]);
        $id = $statement->fetchColumn();
        return $id === false ? null : (int) $id;
    }

    private static function limited(mixed $value, int $max): string
    {
        return mb_substr(trim((string) $value), 0, $max);
    }

    private static function required(mixed $value, int $max, string $label): string
    {
        $clean = self::limited($value, $max);
        if ($clean === '') {
            throw new \InvalidArgumentException("Campo {$label} obbligatorio.");
        }
        return $clean;
    }

    private static function jsonArray(mixed $value): string
    {
        $array = is_array($value) ? array_values($value) : [];
        return json_encode($array, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    }
}
