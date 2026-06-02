<?php
/**
 * Logout API - record session end
 * POST /api/logout.php
 */
header('Content-Type: application/json');
require_once __DIR__ . '/../includes/db.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') { jsonResponse(['error' => 'Method not allowed'], 405); }
if (!authenticateApiKey()) { jsonResponse(['error' => 'Unauthorized'], 401); }

$body      = json_decode(file_get_contents('php://input'), true) ?? [];
$sessionId = (int)($body['session_id'] ?? 0);
$workstation= trim($body['workstation'] ?? '');
$reason    = trim($body['reason'] ?? 'card_removed');

if ($sessionId) {
    db()->prepare('UPDATE sessions SET logged_out_at=NOW(), duration_seconds=TIMESTAMPDIFF(SECOND,logged_in_at,NOW()) WHERE id=? AND logged_out_at IS NULL')
        ->execute([$sessionId]);
}

if ($workstation) {
    db()->prepare('UPDATE workstations SET status="locked", current_user_id=NULL WHERE hostname=?')
        ->execute([$workstation]);
}

logAudit('logout', null, null, $workstation, getClientIp(), $reason);
jsonResponse(['ok' => true]);
