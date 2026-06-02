<?php
/**
 * Shared DB helper + utility functions
 */
require_once __DIR__ . '/../config/database.php';

const LOCK_BACKGROUND_ROTATION_MIN_SECONDS = 30;

function db(): PDO {
    return Database::getConnection();
}

function getSetting(string $key, string $default = ''): string {
    $stmt = db()->prepare('SELECT setting_value FROM settings WHERE setting_key = ?');
    $stmt->execute([$key]);
    $row = $stmt->fetch();
    return $row ? (string)$row['setting_value'] : $default;
}

function getLockBackgroundRotationSeconds(): int {
    $seconds = (int)getSetting('lock_background_rotation_seconds', '300');
    if ($seconds <= 0) {
        $seconds = 300;
    }
    return max(LOCK_BACKGROUND_ROTATION_MIN_SECONDS, $seconds);
}

function getActiveLockBackgroundImage(): string {
    $raw = getSetting('lock_background_image', '');
    $images = array_values(array_filter(array_map(
        static fn(string $value): string => trim($value),
        preg_split('/\R+/', $raw) ?: []
    ), static fn(string $value): bool => $value !== ''));

    if ($images === []) {
        return '';
    }
    if (count($images) === 1) {
        return $images[0];
    }

    $interval = getLockBackgroundRotationSeconds();
    $index = (int)(floor(time() / $interval) % count($images));
    return $images[$index];
}

function getAgentUiSettings(): array {
    return [
        'lock_background_image' => getActiveLockBackgroundImage(),
        'lock_logo_image'       => getSetting('lock_logo_image', ''),
        'lock_brand_name'       => getSetting('lock_brand_name', 'Secure log in'),
        'lock_color_primary'    => getSetting('lock_color_primary', '#2B4D89'),
        'lock_color_panel'      => getSetting('lock_color_panel', '#1D2A43'),
        'lock_color_hex'        => getSetting('lock_color_hex', '#F4F6FA'),
        'lock_color_text'       => getSetting('lock_color_text', '#FFFFFF'),
        'lock_color_hex_left'   => getSetting('lock_color_hex_left', ''),
        'lock_color_hex_top'    => getSetting('lock_color_hex_top', ''),
        'lock_color_hex_bottom' => getSetting('lock_color_hex_bottom', ''),
        'lock_color_overlay'    => getSetting('lock_color_overlay', 'rgba(0,0,0,0.50)'),
        'lock_color_submit'     => getSetting('lock_color_submit', '#c9222e'),
        'lock_hex_logo_image'   => getSetting('lock_hex_logo_image', ''),
        'lock_right_title'      => getSetting('lock_right_title', ''),
        'lock_right_message'    => getSetting('lock_right_message', "Welcome back.\nSingle Sign On is ready when you are."),
    ];
}

function getAgentRuntimeSettings(): array {
    return [
        'lock_on_remove'                      => (bool)(int)getSetting('lock_on_remove', '1'),
        'lock_delay_seconds'                  => (int)getSetting('lock_delay_seconds', '5'),
        'session_timeout_minutes'             => (int)getSetting('session_timeout_minutes', '480'),
        'allow_password_fallback'             => (bool)(int)getSetting('allow_password_fallback', '1'),
        'credential_provider_enabled'         => (bool)(int)getSetting('credential_provider_enabled', '0'),
        'credential_provider_command'         => getSetting('credential_provider_command', ''),
        'credential_provider_timeout_seconds' => (int)getSetting('credential_provider_timeout_seconds', '20'),
        'ui'                                  => getAgentUiSettings(),
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
