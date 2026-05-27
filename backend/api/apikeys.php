<?php
/**
 * API Keys management — GET / POST / DELETE / PATCH
 * Requires admin session (super admin for create/delete).
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();

$pdo    = db();
$method = $_SERVER['REQUEST_METHOD'];

// ── GET  /api/apikeys.php ────────────────────────────────────────────────────
if ($method === 'GET') {
    $keys = $pdo->query(
        "SELECT id, label, api_key, workstation, active, created_at, last_used
         FROM api_keys ORDER BY created_at DESC"
    )->fetchAll();

    // Mask the key for non-super-admins
    if ($_SESSION['admin_role'] !== 'superadmin') {
        foreach ($keys as &$k) {
            $k['api_key'] = substr($k['api_key'], 0, 8) . '••••••••••••••••••••••••';
        }
    }

    jsonResponse($keys);
}

// ── POST /api/apikeys.php  (create) ─────────────────────────────────────────
if ($method === 'POST') {
    requireSuperAdmin();
    $body = json_decode(file_get_contents('php://input'), true) ?? [];

    $label    = trim($body['label'] ?? '');
    $hostname = trim($body['workstation'] ?? '');

    if (!$label) {
        http_response_code(400);
        jsonResponse(['error' => 'label is required.']);
    }

    // Generate a cryptographically random API key
    $newKey = bin2hex(random_bytes(32));          // 64-char hex string

    $stmt = $pdo->prepare(
        'INSERT INTO api_keys (label, api_key, workstation, active) VALUES (?,?,?,1)'
    );
    $stmt->execute([$label, $newKey, $hostname ?: null]);

    logAudit('api_key_created', null, null, $hostname ?: null, getClientIp(), "Key '{$label}' created");
    jsonResponse(['id' => $pdo->lastInsertId(), 'api_key' => $newKey, 'label' => $label]);
}

// ── DELETE /api/apikeys.php?id=X ────────────────────────────────────────────
if ($method === 'DELETE') {
    requireSuperAdmin();
    $id = (int)($_GET['id'] ?? 0);
    if (!$id) { http_response_code(400); jsonResponse(['error' => 'id required']); }

    $key = $pdo->prepare('SELECT label FROM api_keys WHERE id=?');
    $key->execute([$id]);
    $row = $key->fetch();

    if (!$row) { http_response_code(404); jsonResponse(['error' => 'Not found']); }

    $pdo->prepare('DELETE FROM api_keys WHERE id=?')->execute([$id]);
    logAudit('api_key_deleted', null, null, null, getClientIp(), "Key '{$row['label']}' deleted");
    jsonResponse(['success' => true]);
}

// ── PATCH /api/apikeys.php?id=X  (toggle active) ────────────────────────────
if ($method === 'PATCH') {
    requireSuperAdmin();
    $id   = (int)($_GET['id'] ?? 0);
    $body = json_decode(file_get_contents('php://input'), true) ?? [];
    if (!$id) { http_response_code(400); jsonResponse(['error' => 'id required']); }

    $active = isset($body['active']) ? (int)(bool)$body['active'] : null;
    if ($active === null) { http_response_code(400); jsonResponse(['error' => 'active required']); }

    $pdo->prepare('UPDATE api_keys SET active=? WHERE id=?')->execute([$active, $id]);
    jsonResponse(['success' => true]);
}

http_response_code(405);
jsonResponse(['error' => 'Method not allowed']);
