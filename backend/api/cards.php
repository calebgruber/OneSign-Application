<?php
/**
 * Cards API - manage enrolled cards
 */
header('Content-Type: application/json');
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';

requireAdminLogin();

$method = $_SERVER['REQUEST_METHOD'];
$id     = (int)($_GET['id'] ?? 0);

switch ($method) {
    case 'GET':
        if ($id) {
            $stmt = db()->prepare('SELECT c.*, u.username, u.full_name FROM cards c JOIN users u ON c.user_id=u.id WHERE c.id=?');
            $stmt->execute([$id]);
            $row = $stmt->fetch();
            if (!$row) { jsonResponse(['error' => 'Not found'], 404); }
            jsonResponse($row);
        } else {
            $stmt = db()->query('SELECT c.id, c.card_id, c.card_label, c.enrolled_at, c.active, c.last_used,
                u.id AS user_id, u.username, u.full_name
                FROM cards c JOIN users u ON c.user_id=u.id ORDER BY c.enrolled_at DESC');
            jsonResponse($stmt->fetchAll());
        }

    case 'POST':
        $data    = json_decode(file_get_contents('php://input'), true) ?? [];
        $cardId  = strtoupper(trim($data['card_id'] ?? ''));
        $userId  = (int)($data['user_id'] ?? 0);
        $label   = trim($data['card_label'] ?? '');

        if (!$cardId || !$userId) { jsonResponse(['error' => 'card_id and user_id required'], 400); }

        // Check user exists
        $u = db()->prepare('SELECT id FROM users WHERE id=?');
        $u->execute([$userId]);
        if (!$u->fetch()) { jsonResponse(['error' => 'User not found'], 404); }

        // Check card not already enrolled
        $c = db()->prepare('SELECT id FROM cards WHERE card_id=?');
        $c->execute([$cardId]);
        if ($c->fetch()) { jsonResponse(['error' => 'Card already enrolled'], 409); }

        db()->prepare('INSERT INTO cards (user_id, card_id, card_label, enrolled_by) VALUES (?,?,?,?)')
            ->execute([$userId, $cardId, $label, $_SESSION['admin_user']]);
        $newId = db()->lastInsertId();
        logAudit('card_enrolled', $userId, $cardId, null, getClientIp(), "Card enrolled: $label");
        jsonResponse(['id' => (int)$newId, 'ok' => true], 201);

    case 'PUT':
        if (!$id) { jsonResponse(['error' => 'id required'], 400); }
        $data   = json_decode(file_get_contents('php://input'), true) ?? [];
        $fields = [];
        $params = [];
        if (isset($data['card_label'])) { $fields[] = 'card_label=?'; $params[] = $data['card_label']; }
        if (isset($data['active']))     { $fields[] = 'active=?';     $params[] = (int)(bool)$data['active']; }
        if (!$fields) { jsonResponse(['error' => 'Nothing to update'], 400); }
        $params[] = $id;
        db()->prepare('UPDATE cards SET ' . implode(',', $fields) . ' WHERE id=?')->execute($params);
        jsonResponse(['ok' => true]);

    case 'DELETE':
        if (!$id) { jsonResponse(['error' => 'id required'], 400); }
        $c = db()->prepare('SELECT card_id, user_id FROM cards WHERE id=?');
        $c->execute([$id]);
        $row = $c->fetch();
        if ($row) {
            logAudit('card_removed', $row['user_id'], $row['card_id'], null, getClientIp(), 'Card removed');
        }
        db()->prepare('DELETE FROM cards WHERE id=?')->execute([$id]);
        jsonResponse(['ok' => true]);

    default:
        jsonResponse(['error' => 'Method not allowed'], 405);
}
