<?php
/**
 * Card Enrollment API
 * Used by the admin panel to enroll a card via the live PCProx reader
 * POST /api/enroll.php  - Start enrollment mode (agent taps next card and reports it)
 *
 * This endpoint is called from the admin UI. The agent periodically polls
 * GET /api/enroll.php?token=<token> to see if enrollment was requested.
 * Then the agent sends the card ID back:
 * PUT /api/enroll.php  { token, card_id }
 */
header('Content-Type: application/json');
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';

$method = $_SERVER['REQUEST_METHOD'];

// Agent polling - API key auth
if ($method === 'GET') {
    if (!authenticateApiKey()) { jsonResponse(['error' => 'Unauthorized'], 401); }
    // Check if there's a pending enrollment token for this workstation
    $workstation = trim($_GET['workstation'] ?? '');
    if (!$workstation) { jsonResponse(['pending' => false]); }

    $key   = "enroll_pending_$workstation";
    $token = apcu_fetch($key);
    jsonResponse(['pending' => (bool)$token, 'token' => $token ?: null]);
}

// Admin starts enrollment
if ($method === 'POST') {
    requireAdminLogin();
    $data          = json_decode(file_get_contents('php://input'), true) ?? [];
    $workstationId = (int)($data['workstation_id'] ?? 0);
    $workstation   = trim($data['workstation'] ?? '');
    $userId        = (int)($data['user_id'] ?? 0);

    if ($workstationId > 0) {
        $ws = db()->prepare('SELECT hostname FROM workstations WHERE id = ?');
        $ws->execute([$workstationId]);
        $wsRow = $ws->fetch();
        if (!$wsRow) {
            jsonResponse(['error' => 'Selected workstation not found'], 404);
        }
        $workstation = (string)$wsRow['hostname'];
    }

    if (!$workstation || !$userId) { jsonResponse(['error' => 'workstation and user_id required'], 400); }

    $token = bin2hex(random_bytes(16));
    // Store enrollment request (APCu for 5 minutes)
    if (function_exists('apcu_store')) {
        apcu_store("enroll_pending_$workstation", $token, 300);
        apcu_store("enroll_user_$token", $userId, 300);
        apcu_store("enroll_workstation_$token", $workstation, 300);
    }
    jsonResponse(['token' => $token, 'ok' => true, 'workstation' => $workstation]);
}

// Agent submits the tapped card
if ($method === 'PUT') {
    if (!authenticateApiKey()) { jsonResponse(['error' => 'Unauthorized'], 401); }
    $data   = json_decode(file_get_contents('php://input'), true) ?? [];
    $token  = trim($data['token'] ?? '');
    $cardId = strtoupper(trim($data['card_id'] ?? ''));

    if (!$token || !$cardId) { jsonResponse(['error' => 'token and card_id required'], 400); }

    $userId = function_exists('apcu_fetch') ? apcu_fetch("enroll_user_$token") : null;
    if (!$userId) { jsonResponse(['error' => 'Enrollment token expired or not found'], 404); }
    $workstation = function_exists('apcu_fetch') ? apcu_fetch("enroll_workstation_$token") : null;

    // Check if already enrolled
    $existing = db()->prepare('SELECT id FROM cards WHERE card_id=?');
    $existing->execute([$cardId]);
    if ($existing->fetch()) { jsonResponse(['error' => 'Card already enrolled to another user'], 409); }

    db()->prepare('INSERT INTO cards (user_id, card_id, card_label, enrolled_by) VALUES (?,?,?,?)')
        ->execute([$userId, $cardId, 'Badge Card', 'agent']);
    $newId = db()->lastInsertId();

    if (function_exists('apcu_delete')) {
        apcu_delete("enroll_user_$token");
        apcu_delete("enroll_workstation_$token");
        if ($workstation) {
            apcu_delete("enroll_pending_$workstation");
        }
    }

    logAudit('card_enrolled', $userId, $cardId, $workstation ?: null, getClientIp(), 'Card enrolled via agent');
    jsonResponse(['id' => (int)$newId, 'card_id' => $cardId, 'ok' => true, 'workstation' => $workstation], 201);
}

jsonResponse(['error' => 'Method not allowed'], 405);
