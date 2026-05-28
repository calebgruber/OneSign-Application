<?php
/**
 * Lightweight DB-backed runtime key/value store with TTL.
 */
require_once __DIR__ . '/db.php';

function runtimeStoreEnsureTable(): void {
    static $ready = false;
    if ($ready) {
        return;
    }

    db()->exec(
        'CREATE TABLE IF NOT EXISTS runtime_store (
            store_key VARCHAR(191) NOT NULL PRIMARY KEY,
            store_value TEXT NOT NULL,
            expires_at DATETIME DEFAULT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_expires_at (expires_at)
        )'
    );
    $ready = true;
}

function runtimeStoreSet(string $key, mixed $value, int $ttlSeconds = 0): void {
    runtimeStoreEnsureTable();
    $expiresAt = null;
    if ($ttlSeconds > 0) {
        $expiresAt = date('Y-m-d H:i:s', time() + $ttlSeconds);
    }
    $payload = json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if ($payload === false) {
        $payload = 'null';
    }

    db()->prepare(
        'INSERT INTO runtime_store (store_key, store_value, expires_at)
         VALUES (?, ?, ?)
         ON DUPLICATE KEY UPDATE
            store_value = VALUES(store_value),
            expires_at = VALUES(expires_at)'
    )->execute([$key, $payload, $expiresAt]);
}

function runtimeStoreGet(string $key, mixed $default = null): mixed {
    runtimeStoreEnsureTable();

    $stmt = db()->prepare(
        'SELECT store_value
         FROM runtime_store
         WHERE store_key = ?
           AND (expires_at IS NULL OR expires_at > NOW())'
    );
    $stmt->execute([$key]);
    $row = $stmt->fetch();

    if (!$row) {
        runtimeStoreDelete($key);
        return $default;
    }

    $decoded = json_decode((string)$row['store_value'], true);
    return json_last_error() === JSON_ERROR_NONE ? $decoded : $default;
}

function runtimeStoreDelete(string $key): void {
    runtimeStoreEnsureTable();
    db()->prepare('DELETE FROM runtime_store WHERE store_key = ?')->execute([$key]);
}

