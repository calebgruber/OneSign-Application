<?php
/**
 * Settings Page — Tabler UI
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();
$pageTitle = 'Settings';

$saved = false;
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $keys = ['app_name','lock_on_remove','lock_delay_seconds','session_timeout_minutes','allow_password_fallback','enrollment_mode'];
    foreach ($keys as $k) {
        if (isset($_POST[$k])) {
            db()->prepare('UPDATE settings SET setting_value=? WHERE setting_key=?')->execute([$_POST[$k], $k]);
        }
    }
    if (!empty($_POST['encryption_key']) && $_SESSION['admin_role'] === 'superadmin') {
        db()->prepare('UPDATE settings SET setting_value=? WHERE setting_key=?')->execute([$_POST['encryption_key'], 'encryption_key']);
    }
    $saved = true;
}

$rawSettings = db()->query('SELECT setting_key, setting_value FROM settings')->fetchAll();
$s = [];
foreach ($rawSettings as $row) $s[$row['setting_key']] = $row['setting_value'];

include __DIR__ . '/../includes/header.php';
?>

<div class="page-header d-print-none">
  <div class="container-xl">
    <div class="row g-2 align-items-center">
      <div class="col">
        <h2 class="page-title">Settings</h2>
        <div class="text-muted mt-1">Configure OneSign behavior</div>
      </div>
    </div>
  </div>
</div>

<div class="page-body">
  <div class="container-xl">

    <?php if ($saved): ?>
    <div class="alert alert-success alert-dismissible" role="alert">
      <div class="d-flex">
        <i class="ti ti-check me-2"></i>
        <div>Settings saved successfully.</div>
      </div>
      <a class="btn-close" data-bs-dismiss="alert"></a>
    </div>
    <?php endif; ?>

    <form method="post">
    <div class="row row-cards g-4">

      <!-- General -->
      <div class="col-lg-6">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="ti ti-settings me-2 text-blue"></i>General</h3>
          </div>
          <div class="card-body">
            <div class="mb-3">
              <label class="form-label">Application Name</label>
              <input type="text" name="app_name" class="form-control" value="<?= htmlspecialchars($s['app_name'] ?? 'OneSign') ?>">
            </div>
            <div class="mb-3">
              <label class="form-label">Enrollment Mode</label>
              <select name="enrollment_mode" class="form-select">
                <option value="admin" <?= ($s['enrollment_mode']??'admin')==='admin'?'selected':'' ?>>Admin Only</option>
                <option value="user"  <?= ($s['enrollment_mode']??'')==='user' ?'selected':'' ?>>Allow Users to Self-Enroll</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- Lock Behavior -->
      <div class="col-lg-6">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="ti ti-lock me-2 text-blue"></i>Lock Behavior</h3>
          </div>
          <div class="card-body">
            <div class="mb-3">
              <label class="form-check form-switch">
                <input type="hidden" name="lock_on_remove" value="0">
                <input class="form-check-input" type="checkbox" name="lock_on_remove" value="1" id="lockOnRemove"
                  <?= ($s['lock_on_remove'] ?? '1') === '1' ? 'checked' : '' ?>>
                <span class="form-check-label">Lock workstation when badge is removed</span>
              </label>
            </div>
            <div class="mb-3">
              <label class="form-label">Lock delay after badge removal (seconds)</label>
              <input type="number" name="lock_delay_seconds" class="form-control" min="0" max="300"
                value="<?= (int)($s['lock_delay_seconds'] ?? 5) ?>">
            </div>
            <div class="mb-3">
              <label class="form-label">Auto-lock after inactivity (minutes, 0 = disabled)</label>
              <input type="number" name="session_timeout_minutes" class="form-control" min="0"
                value="<?= (int)($s['session_timeout_minutes'] ?? 480) ?>">
            </div>
            <div>
              <label class="form-check form-switch">
                <input type="hidden" name="allow_password_fallback" value="0">
                <input class="form-check-input" type="checkbox" name="allow_password_fallback" value="1" id="pwFallback"
                  <?= ($s['allow_password_fallback'] ?? '1') === '1' ? 'checked' : '' ?>>
                <span class="form-check-label">Allow fallback to Windows username/password login</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <!-- Security (superadmin only) -->
      <?php if ($_SESSION['admin_role'] === 'superadmin'): ?>
      <div class="col-12">
        <div class="card border-danger">
          <div class="card-header bg-red-lt">
            <h3 class="card-title text-danger">
              <i class="ti ti-alert-triangle me-2"></i>Security — Super Admin Only
            </h3>
          </div>
          <div class="card-body">
            <div class="alert alert-warning">
              <i class="ti ti-alert-triangle me-1"></i>
              Changing the encryption key will invalidate all stored Windows passwords. Users must re-enter their passwords after this change.
            </div>
            <div class="mb-0" style="max-width:480px">
              <label class="form-label">Credential Encryption Key</label>
              <div class="input-group input-group-flat">
                <input type="password" name="encryption_key" class="form-control font-monospace" id="encKey"
                  placeholder="Leave blank to keep current key">
                <span class="input-group-text">
                  <a href="#" onclick="togglePw('encKey');return false" class="link-secondary" title="Show key">
                    <i class="ti ti-eye"></i>
                  </a>
                </span>
              </div>
              <div class="form-hint">32+ character random string recommended.</div>
            </div>
          </div>
        </div>
      </div>
      <?php endif; ?>

    </div>

    <div class="mt-4">
      <button type="submit" class="btn btn-primary">
        <i class="ti ti-device-floppy me-1"></i>Save Settings
      </button>
    </div>
    </form>

  </div>
</div>

<?php include __DIR__ . '/../includes/footer.php'; ?>
