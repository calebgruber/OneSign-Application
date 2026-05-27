<?php
/**
 * Settings Page
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
    // Handle encryption key change (only if provided and superadmin)
    if (!empty($_POST['encryption_key']) && $_SESSION['admin_role'] === 'superadmin') {
        db()->prepare('UPDATE settings SET setting_value=? WHERE setting_key=?')->execute([$_POST['encryption_key'], 'encryption_key']);
    }
    $saved = true;
}

// Load all settings
$rawSettings = db()->query('SELECT setting_key, setting_value FROM settings')->fetchAll();
$s = [];
foreach ($rawSettings as $row) $s[$row['setting_key']] = $row['setting_value'];

include __DIR__ . '/../includes/header.php';
?>

<div class="mb-4">
    <h4 class="fw-bold mb-0">Settings</h4>
    <p class="text-muted small mb-0">Configure OneSign behavior</p>
</div>

<?php if ($saved): ?>
<div class="alert alert-success"><i class="bi bi-check-circle me-1"></i>Settings saved successfully.</div>
<?php endif; ?>

<form method="post">
<div class="row g-4">
    <!-- General -->
    <div class="col-lg-6">
        <div class="card border-0 shadow-sm">
            <div class="card-header bg-white border-bottom pt-3">
                <h6 class="fw-semibold mb-0"><i class="bi bi-sliders me-2 text-primary"></i>General</h6>
            </div>
            <div class="card-body">
                <div class="mb-3">
                    <label class="form-label fw-semibold">Application Name</label>
                    <input type="text" name="app_name" class="form-control" value="<?= htmlspecialchars($s['app_name'] ?? 'OneSign') ?>">
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Enrollment Mode</label>
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
        <div class="card border-0 shadow-sm">
            <div class="card-header bg-white border-bottom pt-3">
                <h6 class="fw-semibold mb-0"><i class="bi bi-shield-lock me-2 text-primary"></i>Lock Behavior</h6>
            </div>
            <div class="card-body">
                <div class="mb-3">
                    <div class="form-check form-switch">
                        <input type="hidden" name="lock_on_remove" value="0">
                        <input class="form-check-input" type="checkbox" name="lock_on_remove" value="1" id="lockOnRemove"
                            <?= ($s['lock_on_remove'] ?? '1') === '1' ? 'checked' : '' ?>>
                        <label class="form-check-label fw-semibold" for="lockOnRemove">Lock workstation when card is removed</label>
                    </div>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Lock Delay (seconds after card removal)</label>
                    <input type="number" name="lock_delay_seconds" class="form-control" min="0" max="300" value="<?= (int)($s['lock_delay_seconds'] ?? 5) ?>">
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Auto-lock after inactivity (minutes, 0 = disabled)</label>
                    <input type="number" name="session_timeout_minutes" class="form-control" min="0" value="<?= (int)($s['session_timeout_minutes'] ?? 480) ?>">
                </div>
                <div class="form-check form-switch">
                    <input type="hidden" name="allow_password_fallback" value="0">
                    <input class="form-check-input" type="checkbox" name="allow_password_fallback" value="1" id="pwFallback"
                        <?= ($s['allow_password_fallback'] ?? '1') === '1' ? 'checked' : '' ?>>
                    <label class="form-check-label fw-semibold" for="pwFallback">Allow fallback to Windows username/password login</label>
                </div>
            </div>
        </div>
    </div>

    <!-- Security -->
    <?php if ($_SESSION['admin_role'] === 'superadmin'): ?>
    <div class="col-12">
        <div class="card border-0 shadow-sm border-danger">
            <div class="card-header bg-danger-subtle border-bottom pt-3">
                <h6 class="fw-semibold mb-0 text-danger"><i class="bi bi-exclamation-triangle me-2"></i>Security (Super Admin Only)</h6>
            </div>
            <div class="card-body">
                <div class="alert alert-warning small">
                    <i class="bi bi-exclamation-triangle me-1"></i>
                    Changing the encryption key will invalidate all stored Windows passwords. Users will need to re-enter their passwords after changing this.
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Credential Encryption Key</label>
                    <div class="input-group">
                        <input type="password" name="encryption_key" class="form-control font-monospace" id="encKey" placeholder="Enter new key (leave blank to keep current)">
                        <button class="btn btn-outline-secondary" type="button" onclick="togglePw('encKey')"><i class="bi bi-eye"></i></button>
                    </div>
                    <div class="form-text">Current key is set. 32+ character random string recommended.</div>
                </div>
            </div>
        </div>
    </div>
    <?php endif; ?>
</div>

<div class="mt-4">
    <button type="submit" class="btn btn-primary px-4"><i class="bi bi-save me-1"></i>Save Settings</button>
</div>
</form>

<script>
function togglePw(id) {
    const el = document.getElementById(id);
    el.type = el.type === 'password' ? 'text' : 'password';
}
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
