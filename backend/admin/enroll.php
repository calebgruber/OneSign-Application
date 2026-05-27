<?php
/**
 * Card Enrollment Page - guided flow to enroll a new badge
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();
$pageTitle = 'Enroll Card';
$allUsers  = db()->query('SELECT id, username, full_name FROM users WHERE active=1 ORDER BY full_name')->fetchAll();
include __DIR__ . '/../includes/header.php';
?>

<div class="mb-4">
    <h4 class="fw-bold mb-0">Enroll a Badge / Card</h4>
    <p class="text-muted small mb-0">Follow the steps below to link a physical badge to a Windows user.</p>
</div>

<div class="row g-4">
    <!-- Method 1: Manual entry -->
    <div class="col-lg-6">
        <div class="card border-0 shadow-sm h-100">
            <div class="card-header bg-white border-bottom-0 pt-3">
                <h6 class="fw-semibold"><span class="badge bg-primary me-2">1</span>Manual Card Entry</h6>
            </div>
            <div class="card-body">
                <p class="text-muted small">If you know the card ID (hex), enter it directly below.</p>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Select User *</label>
                    <select class="form-select" id="manualUser">
                        <option value="">— Select User —</option>
                        <?php foreach ($allUsers as $u): ?>
                        <option value="<?= $u['id'] ?>"><?= htmlspecialchars($u['full_name']) ?> (<?= htmlspecialchars($u['username']) ?>)</option>
                        <?php endforeach; ?>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Card ID (Hex) *</label>
                    <input type="text" class="form-control font-monospace" id="manualCardId" placeholder="e.g. A1B2C3D4E5F6">
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Label</label>
                    <input type="text" class="form-control" id="manualLabel" placeholder="ID Badge">
                </div>
                <button class="btn btn-primary w-100" onclick="enrollManual()">
                    <i class="bi bi-credit-card-2-front me-1"></i>Enroll Card
                </button>
                <div id="manualResult" class="mt-3"></div>
            </div>
        </div>
    </div>

    <!-- Method 2: Live reader enrollment -->
    <div class="col-lg-6">
        <div class="card border-0 shadow-sm h-100">
            <div class="card-header bg-white border-bottom-0 pt-3">
                <h6 class="fw-semibold"><span class="badge bg-success me-2">2</span>Live Reader Enrollment</h6>
            </div>
            <div class="card-body">
                <p class="text-muted small">
                    Requires the OneSign agent running on a workstation with a pcProx reader.
                    Select a workstation and user, then tap the badge on the reader.
                </p>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Select User *</label>
                    <select class="form-select" id="liveUser">
                        <option value="">— Select User —</option>
                        <?php foreach ($allUsers as $u): ?>
                        <option value="<?= $u['id'] ?>"><?= htmlspecialchars($u['full_name']) ?> (<?= htmlspecialchars($u['username']) ?>)</option>
                        <?php endforeach; ?>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Workstation (with reader)</label>
                    <input type="text" class="form-control" id="liveWorkstation" placeholder="PC-001">
                </div>
                <button class="btn btn-success w-100" onclick="startLiveEnroll()" id="startLiveBtn">
                    <i class="bi bi-wifi me-1"></i>Start Live Enrollment
                </button>
                <div id="liveStatus" class="mt-3 text-center d-none">
                    <div class="onesign-tap-indicator mb-2">
                        <i class="bi bi-credit-card-2-front"></i>
                    </div>
                    <p class="fw-semibold text-primary">Tap the badge on the pcProx reader now...</p>
                    <div class="spinner-border text-primary spinner-border-sm"></div>
                    <button class="btn btn-sm btn-outline-secondary mt-3" onclick="cancelLiveEnroll()">Cancel</button>
                </div>
                <div id="liveResult" class="mt-3"></div>
            </div>
        </div>
    </div>
</div>

<script>
let liveToken   = null;
let livePoller  = null;

async function enrollManual() {
    const userId = document.getElementById('manualUser').value;
    const cardId = document.getElementById('manualCardId').value.trim().toUpperCase();
    const label  = document.getElementById('manualLabel').value.trim();
    if (!userId || !cardId) { alert('User and Card ID are required.'); return; }

    const r = await fetch('/api/cards.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: parseInt(userId), card_id: cardId, card_label: label || 'Badge Card' }),
    });
    const res = document.getElementById('manualResult');
    if (r.ok) {
        res.innerHTML = `<div class="alert alert-success"><i class="bi bi-check-circle me-1"></i>Card <code>${escHtml(cardId)}</code> enrolled successfully!</div>`;
        document.getElementById('manualCardId').value = '';
    } else {
        const e = await r.json();
        res.innerHTML = `<div class="alert alert-danger"><i class="bi bi-x-circle me-1"></i>${escHtml(e.error || 'Enrollment failed.')}</div>`;
    }
}

async function startLiveEnroll() {
    const userId = document.getElementById('liveUser').value;
    const ws     = document.getElementById('liveWorkstation').value.trim();
    if (!userId || !ws) { alert('User and workstation are required.'); return; }

    const r = await fetch('/api/enroll.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: parseInt(userId), workstation: ws }),
    });
    if (!r.ok) { alert('Failed to start enrollment.'); return; }
    const data = await r.json();
    liveToken = data.token;

    document.getElementById('startLiveBtn').classList.add('d-none');
    document.getElementById('liveStatus').classList.remove('d-none');
    document.getElementById('liveResult').innerHTML = '';

    // Poll for result every 2 seconds (up to 60s)
    let attempts = 0;
    livePoller = setInterval(async () => {
        attempts++;
        if (attempts > 30) { cancelLiveEnroll(); return; }
        // Check audit log for newly enrolled card
        const res = await fetch(`/api/audit.php?type=card_enrolled&limit=5`);
        const events = await res.json();
        if (events.length && Date.now() - new Date(events[0].created_at).getTime() < 10000) {
            clearInterval(livePoller);
            document.getElementById('liveStatus').classList.add('d-none');
            document.getElementById('startLiveBtn').classList.remove('d-none');
            document.getElementById('liveResult').innerHTML =
                `<div class="alert alert-success"><i class="bi bi-check-circle me-1"></i>Card enrolled: <code>${escHtml(events[0].card_id || '')}</code></div>`;
        }
    }, 2000);
}

function cancelLiveEnroll() {
    clearInterval(livePoller);
    liveToken = null;
    document.getElementById('liveStatus').classList.add('d-none');
    document.getElementById('startLiveBtn').classList.remove('d-none');
}
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
