<?php
/**
 * Workstations API — GET list
 * Admin-session-authenticated only (used by admin UI).
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();

$pdo = db();

$search = isset($_GET['search']) ? '%' . $_GET['search'] . '%' : '%';
$status = isset($_GET['status']) ? $_GET['status'] : null;

if ($status) {
    $stmt = $pdo->prepare(
        'SELECT * FROM workstations WHERE (hostname LIKE ? OR ip_address LIKE ?) AND status=? ORDER BY hostname'
    );
    $stmt->execute([$search, $search, $status]);
} else {
    $stmt = $pdo->prepare(
        'SELECT * FROM workstations WHERE hostname LIKE ? OR ip_address LIKE ? ORDER BY hostname'
    );
    $stmt->execute([$search, $search]);
}

$rows = $stmt->fetchAll();

// Add human-readable last_seen
foreach ($rows as &$r) {
    $r['last_seen_relative'] = $r['last_heartbeat']
        ? human_time_diff($r['last_heartbeat'])
        : 'Never';
}

jsonResponse($rows);

/**
 * Human-readable relative time (e.g., "2 minutes ago").
 */
function human_time_diff(string $datetime): string {
    $diff = time() - strtotime($datetime);
    if ($diff < 60)       return 'Just now';
    if ($diff < 3600)     return floor($diff / 60) . ' min ago';
    if ($diff < 86400)    return floor($diff / 3600) . ' hr ago';
    return floor($diff / 86400) . ' days ago';
}
