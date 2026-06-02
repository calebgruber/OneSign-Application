<?php
/**
 * Card Authentication API
 * POST /api/auth.php
 * Headers: X-Api-Key: <key>
 * Body: { "card_id": "AABBCCDD", "workstation": "PC-001", "action": "tap" }
 * Returns: { "authenticated": true, "user": {...}, "credentials": {...} }
 */
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Headers: X-Api-Key, Content-Type');

require_once __DIR__ . '/../includes/db.php';

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(200); exit; }
if ($_SERVER['REQUEST_METHOD'] !== 'POST')    { jsonResponse(['error' => 'Method not allowed'], 405); }

if (!authenticateApiKey()) {
    logAudit('auth_rejected', null, null, null, getClientIp(), 'Invalid API key', false);
    jsonResponse(['error' => 'Unauthorized'], 401);
}

$body = json_decode(file_get_contents('php://input'), true) ?? [];
$cardId     = trim($body['card_id'] ?? '');
$workstation= trim($body['workstation'] ?? '');
$action     = trim($body['action'] ?? 'tap');

if (!$cardId) {
    jsonResponse(['error' => 'card_id is required'], 400);
}

// Look up the card
$stmt = db()->prepare('
    SELECT c.id AS card_id_row, c.card_id, c.active AS card_active,
           u.id, u.username, u.full_name, u.email, u.department,
           u.windows_domain, u.windows_password_enc, u.photo_url, u.active AS user_active
    FROM cards c
    JOIN users u ON c.user_id = u.id
    WHERE c.card_id = ?
');
$stmt->execute([$cardId]);
$row = $stmt->fetch();

if (!$row) {
    logAudit('card_not_found', null, $cardId, $workstation, getClientIp(), 'Card not enrolled', false);
    jsonResponse(['authenticated' => false, 'reason' => 'card_not_found']);
}

if (!$row['card_active']) {
    logAudit('card_disabled', $row['id'], $cardId, $workstation, getClientIp(), 'Card is disabled', false);
    jsonResponse(['authenticated' => false, 'reason' => 'card_disabled']);
}

if (!$row['user_active']) {
    logAudit('user_disabled', $row['id'], $cardId, $workstation, getClientIp(), 'User account disabled', false);
    jsonResponse(['authenticated' => false, 'reason' => 'user_disabled']);
}

// Update card last_used
db()->prepare('UPDATE cards SET last_used = NOW() WHERE card_id = ?')->execute([$cardId]);

// Resolve or create workstation record
$ws = db()->prepare('SELECT id FROM workstations WHERE hostname = ?');
$ws->execute([$workstation]);
$wsRow = $ws->fetch();
if ($wsRow) {
    $wsId = $wsRow['id'];
    db()->prepare('UPDATE workstations SET status = ?, current_user_id = ?, last_heartbeat = NOW(), ip_address = ? WHERE id = ?')
        ->execute(['online', $row['id'], getClientIp(), $wsId]);
} else {
    db()->prepare('INSERT INTO workstations (hostname, ip_address, status, current_user_id, last_heartbeat) VALUES (?,?,?,?,NOW())')
        ->execute([$workstation, getClientIp(), 'online', $row['id']]);
    $wsId = (int)db()->lastInsertId();
}

// Open a session record
db()->prepare('INSERT INTO sessions (user_id, workstation_id, card_id, login_method) VALUES (?,?,?,?)')
    ->execute([$row['id'], $wsId, $cardId, 'card']);
$sessionId = (int)db()->lastInsertId();

logAudit('card_auth_success', $row['id'], $cardId, $workstation, getClientIp(), 'Card authenticated');

// Decrypt credentials if stored
$credentials = null;
if ($row['windows_password_enc']) {
    $decrypted = decryptCredential($row['windows_password_enc']);
    if ($decrypted) {
        $credentials = [
            'username' => $row['username'],
            'domain'   => $row['windows_domain'] ?? '',
            'password' => $decrypted,
        ];
    }
}

jsonResponse([
    'authenticated' => true,
    'session_id'    => $sessionId,
    'user' => [
        'id'         => (int)$row['id'],
        'username'   => $row['username'],
        'full_name'  => $row['full_name'],
        'email'      => $row['email'],
        'department' => $row['department'],
        'photo_url'  => $row['photo_url'],
    ],
    'credentials' => $credentials,
    'settings' => getAgentRuntimeSettings(),
]);
