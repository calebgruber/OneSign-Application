<?php
/**
 * Shared DB helper + utility functions
 */
require_once __DIR__ . '/../config/database.php';

function db(): PDO {
    return Database::getConnection();
}

function getSetting(string $key, string $default = ''): string {
    $stmt = db()->prepare('SELECT setting_value FROM settings WHERE setting_key = ?');
    $stmt->execute([$key]);
    $row = $stmt->fetch();
    return $row ? (string)$row['setting_value'] : $default;
}

function getAgentUiSettings(): array {
    return [
        'lock_background_image' => getSetting('lock_background_image', ''),
        'lock_logo_image'       => getSetting('lock_logo_image', ''),
        'lock_brand_name'       => getSetting('lock_brand_name', 'Secure log in'),
        'lock_color_primary'    => getSetting('lock_color_primary', '#2B4D89'),
        'lock_color_panel'      => getSetting('lock_color_panel', '#1D2A43'),
        'lock_color_hex'        => getSetting('lock_color_hex', '#F4F6FA'),
        'lock_color_text'       => getSetting('lock_color_text', '#FFFFFF'),
    ];
}

function logAudit(string $eventType, ?int $userId, ?string $cardId,
                  ?string $workstation, ?string $ip, ?string $details,
                  bool $success = true): void {
    $stmt = db()->prepare('INSERT INTO audit_log
        (event_type, user_id, card_id, workstation, ip_address, details, success)
        VALUES (?, ?, ?, ?, ?, ?, ?)');
    $stmt->execute([$eventType, $userId, $cardId, $workstation, $ip, $details, $success ? 1 : 0]);
}

function encryptCredential(string $plaintext): string {
    $key  = hash('sha256', CREDENTIAL_ENC_KEY, true);
    $iv   = random_bytes(12);
    $tag  = '';
    $enc  = openssl_encrypt($plaintext, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
    return base64_encode($iv . $tag . $enc);
}

function decryptCredential(string $encoded): ?string {
    $data = base64_decode($encoded);
    if (strlen($data) < 28) return null;
    $iv   = substr($data, 0, 12);
    $tag  = substr($data, 12, 16);
    $enc  = substr($data, 28);
    $key  = hash('sha256', CREDENTIAL_ENC_KEY, true);
    $dec  = openssl_decrypt($enc, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
    return $dec === false ? null : $dec;
}

function jsonResponse(array $data, int $code = 200): void {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode($data);
    exit;
}

function authenticateApiKey(): bool {
    $headers = getallheaders();
    $apiKey  = $headers['X-Api-Key'] ?? ($_SERVER['HTTP_X_API_KEY'] ?? '');
    if (!$apiKey) return false;

    $stmt = db()->prepare('SELECT id FROM api_keys WHERE api_key = ? AND active = 1');
    $stmt->execute([$apiKey]);
    if (!$stmt->fetch()) return false;

    db()->prepare('UPDATE api_keys SET last_used = NOW() WHERE api_key = ?')->execute([$apiKey]);
    return true;
}

function getClientIp(): string {
    return $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '';
}
