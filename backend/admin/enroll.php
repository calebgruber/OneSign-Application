<?php
/**
 * Card Enrollment Page — Tabler UI
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();
$pageTitle = 'Enroll Card';
$allUsers  = db()->query('SELECT id, username, full_name FROM users WHERE active=1 ORDER BY full_name')->fetchAll();
$workstations = db()->query('SELECT id, hostname, status, last_heartbeat FROM workstations ORDER BY hostname')->fetchAll();
include __DIR__ . '/../includes/header.php';
?>

<div class="page-header d-print-none">
  <div class="container-xl">
    <div class="row g-2 align-items-center">
      <div class="col">
        <h2 class="page-title">Enroll a Badge</h2>
        <div class="text-muted mt-1">Link a physical RFID badge to a Windows user account</div>
      </div>
    </div>
  </div>
</div>

<div class="page-body">
  <div class="container-xl">
    <div class="row row-cards g-4">

      <!-- Method 1: Manual -->
      <div class="col-lg-6">
        <div class="card h-100">
          <div class="card-header">
            <h3 class="card-title">
              <span class="badge bg-blue me-2">1</span>Manual Entry
            </h3>
          </div>
          <div class="card-body">
            <p class="text-muted">If you already know the card's hex ID, enter it directly.</p>
            <div class="mb-3">
              <label class="form-label required">User</label>
              <select class="form-select" id="manualUser">
                <option value="">— Select User —</option>
                <?php foreach ($allUsers as $u): ?>
                <option value="<?= $u['id'] ?>"><?= htmlspecialchars($u['full_name']) ?> (<?= htmlspecialchars($u['username']) ?>)</option>
                <?php endforeach; ?>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label required">Card ID (Hex)</label>
              <input type="text" class="form-control font-monospace text-uppercase" id="manualCardId" placeholder="e.g. A1B2C3D4E5F6">
            </div>
            <div class="mb-3">
              <label class="form-label">Label</label>
              <input type="text" class="form-control" id="manualLabel" placeholder="ID Badge">
            </div>
            <button class="btn btn-primary w-100" onclick="enrollManual()">
              <i class="ti ti-id-badge me-1"></i>Enroll Card
            </button>
            <div id="manualResult" class="mt-3"></div>
          </div>
        </div>
      </div>

      <!-- Method 2: Live Reader -->
      <div class="col-lg-6">
        <div class="card h-100">
          <div class="card-header">
            <h3 class="card-title">
              <span class="badge bg-green me-2">2</span>Live Reader Enrollment
            </h3>
          </div>
          <div class="card-body">
            <p class="text-muted">
              Requires the OneSign agent on a workstation with a pcProx reader connected.
              Select a workstation and user, then tap the badge.
            </p>
            <div class="mb-3">
              <label class="form-label required">User</label>
              <select class="form-select" id="liveUser">
                <option value="">— Select User —</option>
                <?php foreach ($allUsers as $u): ?>
                <option value="<?= $u['id'] ?>"><?= htmlspecialchars($u['full_name']) ?> (<?= htmlspecialchars($u['username']) ?>)</option>
                <?php endforeach; ?>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label required">Workstation</label>
              <select class="form-select" id="liveWorkstation">
                <option value="">— Select Workstation —</option>
                <?php foreach ($workstations as $ws):
                  $lastHeartbeatTs = !empty($ws['last_heartbeat']) ? strtotime($ws['last_heartbeat']) : 0;
                  $isOffline = empty($ws['last_heartbeat']) || ((time() - $lastHeartbeatTs) > 90) || (($ws['status'] ?? '') === 'offline');
                  $statusLabel = $isOffline ? 'offline' : ($ws['status'] ?? 'online');
                ?>
                <option value="<?= (int)$ws['id'] ?>" <?= $isOffline ? 'disabled' : '' ?>>
                  <?= htmlspecialchars($ws['hostname']) ?> (<?= htmlspecialchars($statusLabel) ?>)<?= $isOffline ? ' — unavailable' : '' ?>
                </option>
                <?php endforeach; ?>
              </select>
              <?php if (!$workstations): ?>
                <div class="form-hint text-warning">No workstations found yet. Open the Workstations page and wait for an agent heartbeat first.</div>
              <?php endif; ?>
            </div>
            <button class="btn btn-success w-100" onclick="startLiveEnroll()" id="startLiveBtn">
              <i class="ti ti-wifi me-1"></i>Start Live Enrollment
            </button>

            <!-- Waiting animation -->
            <div id="liveStatus" class="text-center py-4 d-none">
              <div class="mb-3">
                <span class="avatar avatar-xl bg-blue-lt text-blue onesign-pulse">
                  <i class="ti ti-id-badge" style="font-size:2rem"></i>
                </span>
              </div>
              <div class="fw-semibold text-blue mb-2">Tap the badge on the reader now&hellip;</div>
              <div class="progress progress-sm mb-3">
                <div class="progress-bar progress-bar-indeterminate bg-blue"></div>
              </div>
              <button class="btn btn-sm btn-outline-secondary" onclick="cancelLiveEnroll()">Cancel</button>
            </div>

            <div id="liveResult" class="mt-2"></div>
          </div>
        </div>
      </div>

    </div>
  </div>
</div>

<script>
let livePoller = null;

async function enrollManual() {
  const userId = document.getElementById('manualUser').value;
  const cardId = document.getElementById('manualCardId').value.trim().toUpperCase();
  const label  = document.getElementById('manualLabel').value.trim();
  if (!userId || !cardId) { alert('User and Card ID are required.'); return; }

  const r   = await fetch('../api/cards.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: parseInt(userId), card_id: cardId, card_label: label || 'Badge Card' }),
  });
  const res = document.getElementById('manualResult');
  if (r.ok) {
    res.innerHTML = `<div class="alert alert-success"><i class="ti ti-check me-1"></i>Card <code>${escHtml(cardId)}</code> enrolled successfully!</div>`;
    document.getElementById('manualCardId').value = '';
  } else {
    const e = await r.json();
    res.innerHTML = `<div class="alert alert-danger"><i class="ti ti-x me-1"></i>${escHtml(e.error || 'Enrollment failed.')}</div>`;
  }
}

async function startLiveEnroll() {
  const userId = document.getElementById('liveUser').value;
  const wsId   = parseInt(document.getElementById('liveWorkstation').value, 10);
  const wsName = document.getElementById('liveWorkstation').selectedOptions[0]?.text || 'selected workstation';
  if (!userId || !wsId) { alert('User and workstation are required.'); return; }

  const r = await fetch('../api/enroll.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: parseInt(userId, 10), workstation_id: wsId }),
  });
  if (!r.ok) { alert('Failed to start enrollment.'); return; }

  document.getElementById('startLiveBtn').classList.add('d-none');
  document.getElementById('liveStatus').classList.remove('d-none');
  document.getElementById('liveResult').innerHTML =
    `<div class="text-muted small">Waiting for badge tap on <strong>${escHtml(wsName)}</strong>.</div>`;

  let attempts = 0;
  livePoller = setInterval(async () => {
    attempts++;
    if (attempts > 30) { cancelLiveEnroll(); return; }
    const evRes = await fetch('../api/audit.php?type=card_enrolled&limit=3');
    const events = await evRes.json();
    if (events.length && (Date.now() - new Date(events[0].created_at).getTime()) < 15000) {
      clearInterval(livePoller);
      document.getElementById('liveStatus').classList.add('d-none');
      document.getElementById('startLiveBtn').classList.remove('d-none');
      document.getElementById('liveResult').innerHTML =
        `<div class="alert alert-success"><i class="ti ti-check me-1"></i>Card enrolled: <code>${escHtml(events[0].card_id || '')}</code></div>`;
    }
  }, 2000);
}

function cancelLiveEnroll() {
  clearInterval(livePoller);
  document.getElementById('liveStatus').classList.add('d-none');
  document.getElementById('startLiveBtn').classList.remove('d-none');
}
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
