<?php
/**
 * Workstations API — GET list
 * Admin-session-authenticated only (used by admin UI).
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();

$pdo = db();
$method = $_SERVER['REQUEST_METHOD'];
$apcuAvailable = function_exists('apcu_fetch') && function_exists('apcu_store');

try {
    if ($method === 'POST') {
        $body = json_decode(file_get_contents('php://input'), true) ?? [];
        $action = trim($body['action'] ?? '');
        if ($action !== 'ping_all') {
            jsonResponse(['error' => 'Unsupported action'], 400);
        }

        if (!$apcuAvailable) {
            jsonResponse([
                'ok' => true,
                'requested' => 0,
                'requested_at' => null,
                'ping_supported' => false,
                'message' => 'Live ping checks are disabled because APCu is not installed',
            ]);
        }

        $rows = $pdo->query('SELECT hostname FROM workstations')->fetchAll();
        $requestedAt = time();
        $count = 0;
        foreach ($rows as $row) {
            $hostname = trim((string)$row['hostname']);
            if ($hostname === '') {
                continue;
            }
            apcu_store("ws_ping_request_$hostname", $requestedAt, 120);
            if (function_exists('apcu_delete')) {
                apcu_delete("ws_ping_ack_$hostname");
            }
            $count++;
        }

        logAudit('workstations_ping_all', null, null, null, getClientIp(), "Requested health ping for {$count} workstation(s)");
        jsonResponse(['ok' => true, 'requested' => $count, 'requested_at' => $requestedAt, 'ping_supported' => true]);
    }

    $search = isset($_GET['search']) ? '%' . $_GET['search'] . '%' : '%';
    $status = isset($_GET['status']) ? $_GET['status'] : null;

    if ($status) {
        $stmt = $pdo->prepare(
            'SELECT w.*, u.full_name AS `current_user`
             FROM workstations w
             LEFT JOIN users u ON w.current_user_id = u.id
             WHERE (w.hostname LIKE ? OR w.ip_address LIKE ?) AND w.status=?
             ORDER BY w.hostname'
        );
        $stmt->execute([$search, $search, $status]);
    } else {
        $stmt = $pdo->prepare(
            'SELECT w.*, u.full_name AS `current_user`
             FROM workstations w
             LEFT JOIN users u ON w.current_user_id = u.id
             WHERE w.hostname LIKE ? OR w.ip_address LIKE ?
             ORDER BY w.hostname'
        );
        $stmt->execute([$search, $search]);
    }

    $rows = $stmt->fetchAll();

    // Add human-readable last_seen
    foreach ($rows as &$r) {
        $r['last_seen_relative'] = $r['last_heartbeat']
            ? human_time_diff((string)$r['last_heartbeat'])
            : 'Never';

        $effective = $r['status'] ?? 'offline';
        if ($r['last_heartbeat']) {
            $hbAge = time() - strtotime((string)$r['last_heartbeat']);
            if ($hbAge > 90) {
                $effective = 'offline';
            }
        } else {
            $effective = 'offline';
        }

        $r['effective_status'] = $effective;
        $r['ping_state'] = 'idle';
        $r['ping_requested_at'] = null;
        $r['ping_acked_at'] = null;
        $r['ping_supported'] = $apcuAvailable;

        if ($apcuAvailable) {
            $hostname = (string)$r['hostname'];
            $requestedAt = apcu_fetch("ws_ping_request_$hostname");
            $ackedAt = apcu_fetch("ws_ping_ack_$hostname");

            if ($requestedAt !== false) {
                $r['ping_requested_at'] = (int)$requestedAt;
                if ($ackedAt !== false) {
                    $r['ping_acked_at'] = (int)$ackedAt;
                }

                if ($ackedAt !== false && (int)$ackedAt >= (int)$requestedAt) {
                    $r['ping_state'] = 'ack';
                } elseif ((time() - (int)$requestedAt) > 60) {
                    $r['ping_state'] = 'timeout';
                    $r['effective_status'] = 'offline';
                } else {
                    $r['ping_state'] = 'pending';
                }
            }
        }
    }
} catch (Throwable $e) {
    error_log('workstations.php error: ' . $e->getMessage());
    jsonResponse(['error' => 'Failed to load workstations'], 500);
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
