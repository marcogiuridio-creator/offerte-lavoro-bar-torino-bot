<?php
declare(strict_types=1);

namespace Horeca;

use PDO;

final class UpdateRepository
{
    public function __construct(private readonly PDO $db) {}

    public function claim(int $updateId): bool
    {
        $statement = $this->db->prepare(
            'INSERT IGNORE INTO telegram_updates (update_id, received_at) VALUES (:update_id, UTC_TIMESTAMP())'
        );
        $statement->execute(['update_id' => $updateId]);
        return $statement->rowCount() === 1;
    }

    public function markProcessed(int $updateId): void
    {
        $statement = $this->db->prepare(
            'UPDATE telegram_updates SET processed_at = UTC_TIMESTAMP() WHERE update_id = :update_id'
        );
        $statement->execute(['update_id' => $updateId]);
    }
}

