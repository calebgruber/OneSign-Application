<?php
/**
 * Admin Login Page
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';

$appBasePath = appBasePath();
$adminBasePath = $appBasePath . '/admin';
$assetBasePath = $appBasePath . '/assets';

if (isAdminLoggedIn()) {
    header('Location: ' . $adminBasePath . '/index.php');
    exit;
}

$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $username = trim($_POST['username'] ?? '');
    $password = $_POST['password'] ?? '';

    $stmt = db()->prepare('SELECT id, username, password_hash, full_name, role FROM admin_users WHERE username=? AND active=1');
    $stmt->execute([$username]);
    $admin = $stmt->fetch();

    if ($admin && password_verify($password, $admin['password_hash'])) {
        session_regenerate_id(true);
        $_SESSION['admin_id']   = $admin['id'];
        $_SESSION['admin_user'] = $admin['username'];
        $_SESSION['admin_name'] = $admin['full_name'];
        $_SESSION['admin_role'] = $admin['role'];
        db()->prepare('UPDATE admin_users SET last_login=NOW() WHERE id=?')->execute([$admin['id']]);
        header('Location: ' . $adminBasePath . '/index.php');
        exit;
    }
    $error = 'Invalid username or password.';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>OneSign &mdash; Admin Login</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0-beta20/dist/css/tabler.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.11.0/dist/tabler-icons.min.css">
<link rel="stylesheet" href="<?= htmlspecialchars($assetBasePath) ?>/css/onesign.css">
</head>
<body class="antialiased d-flex flex-column" style="min-height:100vh; background:var(--tblr-body-bg)">
<div class="page page-center">
  <div class="container container-tight py-4">
    <div class="text-center mb-4">
      <img src="<?= htmlspecialchars($assetBasePath) ?>/img/logo.svg" alt="OneSign" height="56" class="mb-3">
      <h2 class="fw-bold">OneSign Admin</h2>
      <p class="text-muted">Sign in to manage your OneSign deployment</p>
    </div>
    <div class="card card-md shadow-sm">
      <div class="card-body">
        <?php if ($error): ?>
        <div class="alert alert-danger" role="alert">
          <div class="d-flex"><i class="ti ti-alert-triangle me-2 mt-1"></i><?= htmlspecialchars($error) ?></div>
        </div>
        <?php endif; ?>
        <form method="post" autocomplete="off" action="">
          <div class="mb-3">
            <label class="form-label">Username</label>
            <input type="text" name="username" class="form-control" placeholder="admin" required autofocus>
          </div>
          <div class="mb-4">
            <label class="form-label">Password</label>
            <div class="input-group input-group-flat">
              <input type="password" name="password" id="loginPw" class="form-control" placeholder="Your password" required>
              <span class="input-group-text">
                <a href="#" class="link-secondary" onclick="togglePw('loginPw');return false;" title="Show/hide password">
                  <i class="ti ti-eye"></i>
                </a>
              </span>
            </div>
          </div>
          <div class="form-footer">
            <button type="submit" class="btn btn-primary w-100">
              <i class="ti ti-login me-1"></i>Sign in
            </button>
          </div>
        </form>
      </div>
    </div>
    <div class="text-center text-muted mt-3 small">
      OneSign &mdash; Imprivata-compatible tap &amp; go authentication
    </div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0-beta20/dist/js/tabler.min.js"></script>
<script>function togglePw(id){var e=document.getElementById(id);e.type=e.type==='password'?'text':'password';}</script>
</body>
</html>
