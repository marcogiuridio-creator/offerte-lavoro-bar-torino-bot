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
