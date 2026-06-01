<?php
/**
 * Heartbeat API - agent reports status periodically
 * POST /api/heartbeat.php
 */
header('Content-Type: application/json');
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/runtime_store.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') { jsonResponse(['error' => 'Method not allowed'], 405); }
if (!authenticateApiKey()) { jsonResponse(['error' => 'Unauthorized'], 401); }

$body       = json_decode(file_get_contents('php://input'), true) ?? [];
$workstation= trim($body['workstation'] ?? '');
$status     = $body['status'] ?? 'online';
$osVersion  = $body['os_version'] ?? null;
$agentVer   = $body['agent_version'] ?? null;
$ip         = getClientIp();

if (!$workstation) { jsonResponse(['error' => 'workstation required'], 400); }

$allowed = ['online', 'offline', 'locked'];
$status  = in_array($status, $allowed) ? $status : 'online';

$ws = db()->prepare('SELECT id FROM workstations WHERE hostname = ?');
$ws->execute([$workstation]);
$wsRow = $ws->fetch();

if ($wsRow) {
    db()->prepare('UPDATE workstations SET status=?, os_version=COALESCE(?,os_version), agent_version=COALESCE(?,agent_version), last_heartbeat=NOW(), ip_address=? WHERE id=?')
        ->execute([$status, $osVersion, $agentVer, $ip, $wsRow['id']]);
} else {
    db()->prepare('INSERT INTO workstations (hostname, ip_address, os_version, agent_version, status, last_heartbeat) VALUES (?,?,?,?,?,NOW())')
        ->execute([$workstation, $ip, $osVersion, $agentVer, $status]);
}

$pingRequested = false;
$requestedAt = runtimeStoreGet("ws_ping_request_$workstation");
if ($requestedAt !== null) {
    $pingRequested = true;
    runtimeStoreSet("ws_ping_ack_$workstation", time(), 120);
    // Keep the request key so workstations.php can observe both request + ack
    // and correctly display the ping state. The key expires after its 120 s TTL.
}

jsonResponse([
    'ok' => true,
    'ping_requested' => $pingRequested,
    'settings' => [
        'allow_password_fallback' => (bool)(int)getSetting('allow_password_fallback', '1'),
        'session_timeout_minutes' => (int)getSetting('session_timeout_minutes', '480'),
        'ui' => getAgentUiSettings(),
    ],
]);
