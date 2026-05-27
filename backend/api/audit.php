<?php
/**
 * Audit Log API
 */
header('Content-Type: application/json');
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';

requireAdminLogin();

$limit  = min((int)($_GET['limit'] ?? 100), 1000);
$offset = (int)($_GET['offset'] ?? 0);
$userId = (int)($_GET['user_id'] ?? 0);
$type   = trim($_GET['type'] ?? '');

$where  = [];
$params = [];
if ($userId) { $where[] = 'a.user_id=?'; $params[] = $userId; }
if ($type)   { $where[] = 'a.event_type=?'; $params[] = $type; }

$sql = 'SELECT a.id, a.event_type, a.card_id, a.workstation, a.ip_address, a.details, a.success, a.created_at,
        u.username, u.full_name
        FROM audit_log a LEFT JOIN users u ON a.user_id=u.id'
    . ($where ? ' WHERE ' . implode(' AND ', $where) : '')
    . ' ORDER BY a.created_at DESC LIMIT ? OFFSET ?';
$params[] = $limit;
$params[] = $offset;

$stmt = db()->prepare($sql);
$stmt->execute($params);
jsonResponse($stmt->fetchAll());
