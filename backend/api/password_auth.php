<?php
/**
 * Username/password authentication API for lock overlay fallback.
 * POST /api/password_auth.php
 * Body: { "username": "...", "password": "...", "workstation": "PC-001" }
 */
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Headers: X-Api-Key, Content-Type');

require_once __DIR__ . '/../includes/db.php';

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(200); exit; }
if ($_SERVER['REQUEST_METHOD'] !== 'POST')    { jsonResponse(['error' => 'Method not allowed'], 405); }

if (!authenticateApiKey()) {
    logAudit('password_auth_rejected', null, null, null, getClientIp(), 'Invalid API key', false);
    jsonResponse(['error' => 'Unauthorized'], 401);
}

if ((int)getSetting('allow_password_fallback', '1') !== 1) {
    jsonResponse(['authenticated' => false, 'reason' => 'password_fallback_disabled'], 403);
}

$body = json_decode(file_get_contents('php://input'), true) ?? [];
$username = trim((string)($body['username'] ?? ''));
$password = (string)($body['password'] ?? '');
$workstation = trim((string)($body['workstation'] ?? ''));

if ($username === '' || $password === '') {
    jsonResponse(['error' => 'username and password are required'], 400);
}

$resolvedCredentials = null;
$authRow = null;
$authMethod = 'password';

$emergencyUsername = trim((string)getSetting('emergency_unlock_username', ''));
$emergencyDomain = trim((string)getSetting('emergency_unlock_domain', '.'));
$emergencyPasswordEnc = (string)getSetting('emergency_unlock_password_enc', '');
$emergencyPassword = $emergencyPasswordEnc !== '' ? (string)(decryptCredential($emergencyPasswordEnc) ?? '') : '';

if (
    $emergencyUsername !== '' &&
    $emergencyPassword !== '' &&
    strcasecmp($username, $emergencyUsername) === 0 &&
    hash_equals($password, $emergencyPassword)
) {
    $stmt = db()->prepare('
        SELECT id, username, full_name, email, department, windows_domain, active
        FROM users
        WHERE username = ?
        LIMIT 1
    ');
    $stmt->execute([$emergencyUsername]);
    $authRow = $stmt->fetch();

    if (!$authRow || !(int)$authRow['active']) {
        logAudit('password_auth_failed', null, null, $workstation, getClientIp(), 'Emergency credentials configured without active mapped user', false);
        jsonResponse(['authenticated' => false, 'reason' => 'invalid_credentials']);
    }

    $resolvedCredentials = [
        'username' => $emergencyUsername,
        'domain'   => $emergencyDomain !== '' ? $emergencyDomain : '.',
        'password' => $emergencyPassword,
    ];
    $authMethod = 'emergency';
}

if ($authRow === null) {
    $stmt = db()->prepare('
        SELECT id, username, full_name, email, department, windows_domain, windows_password_enc, active
        FROM users
        WHERE username = ?
        LIMIT 1
    ');
    $stmt->execute([$username]);
    $authRow = $stmt->fetch();

    if (!$authRow || !(int)$authRow['active']) {
        logAudit('password_auth_failed', null, null, $workstation, getClientIp(), 'Unknown or inactive user', false);
        jsonResponse(['authenticated' => false, 'reason' => 'invalid_credentials']);
    }

    $storedPassword = '';
    if (!empty($authRow['windows_password_enc'])) {
        $storedPassword = (string)(decryptCredential($authRow['windows_password_enc']) ?? '');
    }
    if ($storedPassword === '' || !hash_equals($password, $storedPassword)) {
        logAudit('password_auth_failed', (int)$authRow['id'], null, $workstation, getClientIp(), 'Invalid password', false);
        jsonResponse(['authenticated' => false, 'reason' => 'invalid_credentials']);
    }

    $resolvedCredentials = [
        'username' => $authRow['username'],
        'domain'   => $authRow['windows_domain'] ?? '',
        'password' => $storedPassword,
    ];
}

// Resolve or create workstation record
$ws = db()->prepare('SELECT id FROM workstations WHERE hostname = ?');
$ws->execute([$workstation]);
$wsRow = $ws->fetch();
if ($wsRow) {
    $wsId = (int)$wsRow['id'];
    db()->prepare('UPDATE workstations SET status = ?, current_user_id = ?, last_heartbeat = NOW(), ip_address = ? WHERE id = ?')
        ->execute(['online', (int)$authRow['id'], getClientIp(), $wsId]);
} else {
    db()->prepare('INSERT INTO workstations (hostname, ip_address, status, current_user_id, last_heartbeat) VALUES (?,?,?,?,NOW())')
        ->execute([$workstation, getClientIp(), 'online', (int)$authRow['id']]);
    $wsId = (int)db()->lastInsertId();
}

db()->prepare('INSERT INTO sessions (user_id, workstation_id, card_id, login_method) VALUES (?,?,?,?)')
    ->execute([(int)$authRow['id'], $wsId, null, $authMethod]);
$sessionId = (int)db()->lastInsertId();

logAudit('password_auth_success', (int)$authRow['id'], null, $workstation, getClientIp(), 'Password fallback authentication');

jsonResponse([
    'authenticated' => true,
    'session_id' => $sessionId,
    'user' => [
        'id'         => (int)$authRow['id'],
        'username'   => $authRow['username'],
        'full_name'  => $authRow['full_name'],
        'email'      => $authRow['email'],
        'department' => $authRow['department'],
    ],
    'credentials' => $resolvedCredentials,
    'settings' => [
        'allow_password_fallback' => (bool)(int)getSetting('allow_password_fallback', '1'),
        'session_timeout_minutes' => (int)getSetting('session_timeout_minutes', '480'),
        'ui' => getAgentUiSettings(),
    ],
]);
