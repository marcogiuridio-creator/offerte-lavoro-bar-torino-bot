<?php
declare(strict_types=1);

use Horeca\Bootstrap;

require dirname(__DIR__) . '/src/Bootstrap.php';

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}
if ($argc !== 2 || !is_file($argv[1])) {
    fwrite(STDERR, "Uso: php database/import_mysql.php export.json\n");
    exit(2);
}

$allowed = [
    'users', 'posts', 'banned_words', 'stats_daily', 'bot_settings',
    'candidate_profiles', 'job_offers', 'applications', 'security_events', 'payment_events',
];
$decoded = json_decode((string) file_get_contents($argv[1]), true, 64, JSON_THROW_ON_ERROR);
if (($decoded['format'] ?? null) !== 1 || !is_array($decoded['tables'] ?? null)) {
    throw new RuntimeException('Formato esportazione non valido.');
}

$db = Bootstrap::db();
$db->beginTransaction();
$counts = [];
try {
    $db->exec('SET FOREIGN_KEY_CHECKS=0');
    foreach ($allowed as $table) {
        $rows = $decoded['tables'][$table] ?? [];
        if (!is_array($rows)) {
            throw new RuntimeException("Tabella {$table} non valida.");
        }
        $counts[$table] = 0;
        foreach ($rows as $row) {
            if (!is_array($row) || $row === []) {
                continue;
            }
            $columns = array_keys($row);
            foreach ($columns as $column) {
                if (!preg_match('/^[a-z_][a-z0-9_]*$/', (string) $column)) {
                    throw new RuntimeException('Nome colonna non valido.');
                }
            }
            $quoted = array_map(static fn ($column) => "`{$column}`", $columns);
            $params = array_map(static fn ($column) => ":{$column}", $columns);
            $updates = array_map(static fn ($column) => "`{$column}`=VALUES(`{$column}`)", $columns);
            $sql = sprintf(
                'INSERT INTO `%s` (%s) VALUES (%s) ON DUPLICATE KEY UPDATE %s',
                $table, implode(',', $quoted), implode(',', $params), implode(',', $updates)
            );
            $db->prepare($sql)->execute($row);
            $counts[$table]++;
        }
    }
    $db->exec('SET FOREIGN_KEY_CHECKS=1');
    $db->commit();
} catch (Throwable $error) {
    if ($db->inTransaction()) {
        $db->rollBack();
    }
    throw $error;
}

echo json_encode(['status' => 'ok', 'counts' => $counts], JSON_PRETTY_PRINT) . PHP_EOL;

