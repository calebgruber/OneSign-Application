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

$stmt = db()->prepare('
    SELECT id, username, full_name, email, department, windows_domain, windows_password_enc, active
    FROM users
    WHERE username = ?
    LIMIT 1
');
$stmt->execute([$username]);
$row = $stmt->fetch();

if (!$row || !(int)$row['active']) {
    logAudit('password_auth_failed', null, null, $workstation, getClientIp(), 'Unknown or inactive user', false);
    jsonResponse(['authenticated' => false, 'reason' => 'invalid_credentials']);
}

$storedPassword = '';
if (!empty($row['windows_password_enc'])) {
    $storedPassword = (string)(decryptCredential($row['windows_password_enc']) ?? '');
}
if ($storedPassword === '' || !hash_equals($storedPassword, $password)) {
    logAudit('password_auth_failed', (int)$row['id'], null, $workstation, getClientIp(), 'Invalid password', false);
    jsonResponse(['authenticated' => false, 'reason' => 'invalid_credentials']);
}

// Resolve or create workstation record
$ws = db()->prepare('SELECT id FROM workstations WHERE hostname = ?');
$ws->execute([$workstation]);
$wsRow = $ws->fetch();
if ($wsRow) {
    $wsId = (int)$wsRow['id'];
    db()->prepare('UPDATE workstations SET status = ?, current_user_id = ?, last_heartbeat = NOW(), ip_address = ? WHERE id = ?')
        ->execute(['online', (int)$row['id'], getClientIp(), $wsId]);
} else {
    db()->prepare('INSERT INTO workstations (hostname, ip_address, status, current_user_id, last_heartbeat) VALUES (?,?,?,?,NOW())')
        ->execute([$workstation, getClientIp(), 'online', (int)$row['id']]);
    $wsId = (int)db()->lastInsertId();
}

db()->prepare('INSERT INTO sessions (user_id, workstation_id, card_id, login_method) VALUES (?,?,?,?)')
    ->execute([(int)$row['id'], $wsId, null, 'password']);
$sessionId = (int)db()->lastInsertId();

logAudit('password_auth_success', (int)$row['id'], null, $workstation, getClientIp(), 'Password fallback authentication');

jsonResponse([
    'authenticated' => true,
    'session_id' => $sessionId,
    'user' => [
        'id'         => (int)$row['id'],
        'username'   => $row['username'],
        'full_name'  => $row['full_name'],
        'email'      => $row['email'],
        'department' => $row['department'],
    ],
    'credentials' => [
        'username' => $row['username'],
        'domain'   => $row['windows_domain'] ?? '',
        'password' => $storedPassword,
    ],
    'settings' => [
        'ui' => getAgentUiSettings(),
    ],
]);
