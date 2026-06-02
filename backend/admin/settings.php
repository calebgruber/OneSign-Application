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
    $keys = [
        'app_name',
        'lock_on_remove',
        'lock_delay_seconds',
        'session_timeout_minutes',
        'allow_password_fallback',
        'enrollment_mode',
        'credential_provider_enabled',
        'credential_provider_command',
        'credential_provider_timeout_seconds',
        'lock_background_image',
        'lock_background_rotation_seconds',
        'lock_logo_image',
        'lock_hex_logo_image',
        'lock_brand_name',
        'lock_color_primary',
        'lock_color_panel',
        'lock_color_hex',
        'lock_color_text',
        'lock_color_hex_left',
        'lock_color_hex_top',
        'lock_color_hex_bottom',
        'lock_color_overlay',
        'lock_color_submit',
        'lock_right_title',
        'lock_right_message',
        'emergency_unlock_username',
        'emergency_unlock_domain',
    ];
    foreach ($keys as $k) {
        if (isset($_POST[$k])) {
            db()->prepare('
                INSERT INTO settings (setting_key, setting_value, description)
                VALUES (?, ?, ?)
                ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
            ')->execute([$k, (string)$_POST[$k], '']);
        }
    }
    if (!empty($_POST['encryption_key']) && $_SESSION['admin_role'] === 'superadmin') {
        db()->prepare('UPDATE settings SET setting_value=? WHERE setting_key=?')->execute([$_POST['encryption_key'], 'encryption_key']);
    }
    if (isset($_POST['emergency_unlock_password']) && trim((string)$_POST['emergency_unlock_password']) !== '') {
        $encEmergency = encryptCredential((string)$_POST['emergency_unlock_password']);
        db()->prepare('
            INSERT INTO settings (setting_key, setting_value, description)
            VALUES (?, ?, ?)
            ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
        ')->execute(['emergency_unlock_password_enc', $encEmergency, '']);
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

      <!-- Credential Provider -->
      <div class="col-12">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="ti ti-plug me-2 text-blue"></i>Credential Provider</h3>
          </div>
          <div class="card-body">
            <p class="text-muted small mb-3">
              When enabled, the agent invokes an external helper process to unlock the workstation instead of
              sending keystrokes directly. The helper receives a JSON payload on stdin
              (<code>{"username":"…","password":"…","domain":"…"}</code>) and must exit with code&nbsp;0 on success.
            </p>
            <div class="mb-3">
              <label class="form-check form-switch">
                <input type="hidden" name="credential_provider_enabled" value="0">
                <input class="form-check-input" type="checkbox" name="credential_provider_enabled" value="1" id="cpEnabled"
                  <?= ($s['credential_provider_enabled'] ?? '0') === '1' ? 'checked' : '' ?>>
                <span class="form-check-label">Enable external credential provider helper</span>
              </label>
            </div>
            <div class="mb-3" style="max-width:600px">
              <label class="form-label">Helper Command</label>
              <input type="text" name="credential_provider_command" class="form-control font-monospace"
                placeholder="e.g. C:\OneSign\cp_helper.exe"
                value="<?= htmlspecialchars($s['credential_provider_command'] ?? '') ?>">
              <div class="form-hint">Full path to the credential provider helper executable.</div>
            </div>
            <div style="max-width:200px">
              <label class="form-label">Helper timeout (seconds)</label>
              <input type="number" name="credential_provider_timeout_seconds" class="form-control" min="1" max="120"
                value="<?= (int)($s['credential_provider_timeout_seconds'] ?? 20) ?>">
            </div>
          </div>
        </div>
      </div>

      <!-- Lock Screen Branding -->
      <div class="col-12">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="ti ti-palette me-2 text-blue"></i>Lock Screen Branding</h3>
          </div>
          <div class="card-body">
            <p class="text-muted small mb-3">
              These settings are synced by agents and applied to the full-screen lock overlay.
            </p>
            <div class="row g-3">
              <div class="col-lg-6">
                <label class="form-label">Background image URLs <small class="text-muted">(one per line; rotates for every agent together)</small></label>
                <textarea name="lock_background_image" class="form-control" rows="4"
                  placeholder="https://example.com/slide-1.jpg&#10;https://example.com/slide-2.jpg"><?= htmlspecialchars($s['lock_background_image'] ?? '') ?></textarea>
              </div>
              <div class="col-lg-2">
                <label class="form-label">Slide interval (seconds)</label>
                <input type="number" name="lock_background_rotation_seconds" class="form-control" min="30" max="86400"
                  value="<?= (int)($s['lock_background_rotation_seconds'] ?? 300) ?>">
              </div>
              <div class="col-lg-6">
                <label class="form-label">Logo image URL</label>
                <input type="url" name="lock_logo_image" class="form-control"
                  placeholder="https://..."
                  value="<?= htmlspecialchars($s['lock_logo_image'] ?? '') ?>">
              </div>
              <div class="col-lg-6">
                <label class="form-label">Hex cluster logo URL <small class="text-muted">(left hexagon; defaults to logo image)</small></label>
                <input type="url" name="lock_hex_logo_image" class="form-control"
                  placeholder="https://..."
                  value="<?= htmlspecialchars($s['lock_hex_logo_image'] ?? '') ?>">
              </div>
              <div class="col-lg-4">
                <label class="form-label">Brand text</label>
                <input type="text" name="lock_brand_name" class="form-control"
                  value="<?= htmlspecialchars($s['lock_brand_name'] ?? 'Secure log in') ?>">
              </div>
              <div class="col-lg-4">
                <label class="form-label">Right panel title <small class="text-muted">(leave blank to hide)</small></label>
                <input type="text" name="lock_right_title" class="form-control"
                  placeholder="(hidden when empty)"
                  value="<?= htmlspecialchars($s['lock_right_title'] ?? '') ?>">
              </div>
              <div class="col-lg-4">
                <label class="form-label">Right panel message</label>
                <input type="text" name="lock_right_message" class="form-control"
                  value="<?= htmlspecialchars($s['lock_right_message'] ?? 'Welcome back.\nSingle Sign On is ready when you are.') ?>">
              </div>
              <div class="col-lg-2">
                <label class="form-label">Primary color</label>
                <input type="color" name="lock_color_primary" class="form-control form-control-color"
                  value="<?= htmlspecialchars($s['lock_color_primary'] ?? '#2B4D89') ?>">
              </div>
              <div class="col-lg-2">
                <label class="form-label">Right panel color</label>
                <input type="color" name="lock_color_panel" class="form-control form-control-color"
                  value="<?= htmlspecialchars($s['lock_color_panel'] ?? '#1D2A43') ?>">
              </div>
              <div class="col-lg-2">
                <label class="form-label">Hex card color</label>
                <input type="color" name="lock_color_hex" class="form-control form-control-color"
                  value="<?= htmlspecialchars($s['lock_color_hex'] ?? '#F4F6FA') ?>">
              </div>
              <div class="col-lg-2">
                <label class="form-label">Left hex color</label>
                <input type="color" name="lock_color_hex_left" class="form-control form-control-color"
                  value="<?= htmlspecialchars($s['lock_color_hex_left'] ?? '#2B4D89') ?>">
              </div>
              <div class="col-lg-2">
                <label class="form-label">Top hex color</label>
                <input type="color" name="lock_color_hex_top" class="form-control form-control-color"
                  value="<?= htmlspecialchars($s['lock_color_hex_top'] ?? '#1D2A43') ?>">
              </div>
              <div class="col-lg-2">
                <label class="form-label">Bottom hex color</label>
                <input type="color" name="lock_color_hex_bottom" class="form-control form-control-color"
                  value="<?= htmlspecialchars($s['lock_color_hex_bottom'] ?? '#1D2A43') ?>">
              </div>
              <div class="col-lg-2">
                <label class="form-label">Text color</label>
                <input type="color" name="lock_color_text" class="form-control form-control-color"
                  value="<?= htmlspecialchars($s['lock_color_text'] ?? '#FFFFFF') ?>">
              </div>
              <div class="col-lg-2">
                <label class="form-label">Submit button</label>
                <input type="color" name="lock_color_submit" class="form-control form-control-color"
                  value="<?= htmlspecialchars($s['lock_color_submit'] ?? '#c9222e') ?>">
              </div>
              <div class="col-lg-4">
                <label class="form-label">Overlay color (CSS color)</label>
                <input type="text" name="lock_color_overlay" class="form-control"
                  placeholder="rgba(0,0,0,0.50)"
                  value="<?= htmlspecialchars($s['lock_color_overlay'] ?? 'rgba(0,0,0,0.50)') ?>">
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="col-12">
        <div class="card border-warning">
          <div class="card-header">
            <h3 class="card-title"><i class="ti ti-key me-2 text-yellow"></i>Emergency Unlock Credentials</h3>
          </div>
          <div class="card-body">
            <p class="text-muted small mb-3">
              These credentials can be used as a backend emergency override on locked workstations.
            </p>
            <div class="row g-3">
              <div class="col-lg-4">
                <label class="form-label">Emergency username</label>
                <input type="text" name="emergency_unlock_username" class="form-control"
                  value="<?= htmlspecialchars($s['emergency_unlock_username'] ?? '') ?>">
              </div>
              <div class="col-lg-2">
                <label class="form-label">Emergency domain</label>
                <input type="text" name="emergency_unlock_domain" class="form-control"
                  value="<?= htmlspecialchars($s['emergency_unlock_domain'] ?? '.') ?>">
              </div>
              <div class="col-lg-4">
                <label class="form-label">Emergency password</label>
                <input type="password" name="emergency_unlock_password" class="form-control"
                  placeholder="Leave blank to keep current password">
                <div class="form-hint">Stored encrypted on save.</div>
              </div>
            </div>
          </div>
        </div>
      </div>

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
