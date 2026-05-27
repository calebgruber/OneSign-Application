<?php
/**
 * Admin session authentication check
 */
require_once __DIR__ . '/../config/config.php';

if (session_status() === PHP_SESSION_NONE) {
    session_set_cookie_params([
        'lifetime' => SESSION_LIFETIME,
        'path'     => '/',
        'secure'   => false,
        'httponly' => true,
        'samesite' => 'Strict',
    ]);
    session_start();
}

function isAdminLoggedIn(): bool {
    return !empty($_SESSION['admin_id']) && !empty($_SESSION['admin_user']);
}

function requireAdminLogin(): void {
    if (!isAdminLoggedIn()) {
        header('Location: /admin/login.php');
        exit;
    }
}

function requireSuperAdmin(): void {
    requireAdminLogin();
    if (($_SESSION['admin_role'] ?? '') !== 'superadmin') {
        http_response_code(403);
        die('Access denied.');
    }
}
