<?php
/**
 * Users API - CRUD for Windows users
 * Requires admin session (called from admin panel JS)
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
            $stmt = db()->prepare('SELECT id, username, full_name, email, department, windows_domain, photo_url, active, created_at FROM users WHERE id=?');
            $stmt->execute([$id]);
            $user = $stmt->fetch();
            if (!$user) { jsonResponse(['error' => 'Not found'], 404); }
            // Attach cards
            $cards = db()->prepare('SELECT id, card_id, card_label, enrolled_at, active, last_used FROM cards WHERE user_id=?');
            $cards->execute([$id]);
            $user['cards'] = $cards->fetchAll();
            jsonResponse($user);
        } else {
            $stmt = db()->query('SELECT u.id, u.username, u.full_name, u.email, u.department, u.active, u.created_at,
                (SELECT COUNT(*) FROM cards c WHERE c.user_id=u.id AND c.active=1) AS card_count
                FROM users u ORDER BY u.full_name');
            jsonResponse($stmt->fetchAll());
        }

    case 'POST':
        $data = json_decode(file_get_contents('php://input'), true) ?? [];
        $username = trim($data['username'] ?? '');
        $fullName = trim($data['full_name'] ?? '');
        $email    = trim($data['email'] ?? '');
        $dept     = trim($data['department'] ?? '');
        $domain   = trim($data['windows_domain'] ?? '');
        $password = $data['windows_password'] ?? '';
        $active   = isset($data['active']) ? (int)(bool)$data['active'] : 1;

        if (!$username || !$fullName) { jsonResponse(['error' => 'username and full_name required'], 400); }

        $pwdEnc = $password ? encryptCredential($password) : null;

        db()->prepare('INSERT INTO users (username, full_name, email, department, windows_domain, windows_password_enc, active) VALUES (?,?,?,?,?,?,?)')
            ->execute([$username, $fullName, $email, $dept, $domain, $pwdEnc, $active]);
        $newId = db()->lastInsertId();
        logAudit('user_created', (int)$newId, null, null, getClientIp(), "User $username created");
        jsonResponse(['id' => (int)$newId, 'ok' => true], 201);

    case 'PUT':
        if (!$id) { jsonResponse(['error' => 'id required'], 400); }
        $data = json_decode(file_get_contents('php://input'), true) ?? [];
        $fields = [];
        $params = [];
        if (isset($data['full_name']))       { $fields[] = 'full_name=?';           $params[] = $data['full_name']; }
        if (isset($data['email']))           { $fields[] = 'email=?';               $params[] = $data['email']; }
        if (isset($data['department']))      { $fields[] = 'department=?';          $params[] = $data['department']; }
        if (isset($data['windows_domain']))  { $fields[] = 'windows_domain=?';      $params[] = $data['windows_domain']; }
        if (isset($data['active']))          { $fields[] = 'active=?';              $params[] = (int)(bool)$data['active']; }
        if (!empty($data['windows_password'])){ $fields[] = 'windows_password_enc=?'; $params[] = encryptCredential($data['windows_password']); }
        if (!$fields) { jsonResponse(['error' => 'Nothing to update'], 400); }
        $params[] = $id;
        db()->prepare('UPDATE users SET ' . implode(',', $fields) . ' WHERE id=?')->execute($params);
        logAudit('user_updated', $id, null, null, getClientIp(), 'User updated');
        jsonResponse(['ok' => true]);

    case 'DELETE':
        if (!$id) { jsonResponse(['error' => 'id required'], 400); }
        if (($_SESSION['admin_role'] ?? '') !== 'superadmin') { jsonResponse(['error' => 'Forbidden'], 403); }
        db()->prepare('DELETE FROM users WHERE id=?')->execute([$id]);
        logAudit('user_deleted', $id, null, null, getClientIp(), 'User deleted');
        jsonResponse(['ok' => true]);

    default:
        jsonResponse(['error' => 'Method not allowed'], 405);
}
