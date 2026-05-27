<?php
/**
 * Card Management — Tabler UI
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();
$pageTitle = 'Cards';
$allUsers  = db()->query('SELECT id, username, full_name FROM users WHERE active=1 ORDER BY full_name')->fetchAll();
include __DIR__ . '/../includes/header.php';
?>

<div class="page-header d-print-none">
  <div class="container-xl">
    <div class="row g-2 align-items-center">
      <div class="col">
        <h2 class="page-title">Enrolled Cards</h2>
        <div class="text-muted mt-1">RFID/proximity badges linked to Windows users</div>
      </div>
      <div class="col-auto ms-auto">
        <button class="btn btn-primary" onclick="showCardModal()">
          <i class="ti ti-id-badge me-1"></i>Add Card
        </button>
      </div>
    </div>
  </div>
</div>

<div class="page-body">
  <div class="container-xl">
    <div class="card">
      <div class="card-header">
        <div class="input-group input-group-sm w-auto ms-auto">
          <input type="text" class="form-control" placeholder="Search…" oninput="filterTable('cards-tbody', this.value)">
          <span class="input-group-text"><i class="ti ti-search"></i></span>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table table-vcenter card-table">
          <thead>
            <tr>
              <th>Card ID</th>
              <th>Label</th>
              <th>User</th>
              <th>Enrolled</th>
              <th>Last Used</th>
              <th class="text-center">Status</th>
              <th class="text-end">Actions</th>
            </tr>
          </thead>
          <tbody id="cards-tbody">
            <tr><td colspan="7" class="text-center text-muted py-4">
              <div class="spinner-border spinner-border-sm me-2"></div>Loading…
            </td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<!-- Card Modal -->
<div class="modal modal-blur fade" id="cardModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Add Card</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <div class="mb-3">
          <label class="form-label required">Card ID (Hex)</label>
          <input type="text" class="form-control font-monospace text-uppercase" id="cCardId" placeholder="e.g. A1B2C3D4">
          <div class="form-hint">Tap a card on the reader to read its ID, or use the Enroll page.</div>
        </div>
        <div class="mb-3">
          <label class="form-label required">Assign to User</label>
          <select class="form-select" id="cUserId">
            <option value="">— Select User —</option>
            <?php foreach ($allUsers as $u): ?>
            <option value="<?= $u['id'] ?>"><?= htmlspecialchars($u['full_name']) ?> (<?= htmlspecialchars($u['username']) ?>)</option>
            <?php endforeach; ?>
          </select>
        </div>
        <div class="mb-3">
          <label class="form-label">Label</label>
          <input type="text" class="form-control" id="cLabel" placeholder="ID Badge">
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-link link-secondary me-auto" data-bs-dismiss="modal">Cancel</button>
        <button class="btn btn-primary" onclick="saveCard()">
          <i class="ti ti-device-floppy me-1"></i>Save Card
        </button>
      </div>
    </div>
  </div>
</div>

<script>
const cardModal = new bootstrap.Modal(document.getElementById('cardModal'));

async function loadCards() {
  const res  = await fetch('/api/cards.php');
  const data = await res.json();
  const tbody = document.getElementById('cards-tbody');
  if (!data.length) { tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">No cards enrolled.</td></tr>'; return; }
  tbody.innerHTML = data.map(c => `
    <tr data-search="${escHtml((c.card_id+' '+(c.card_label||'')+' '+c.full_name+' '+c.username).toLowerCase())}">
      <td><code>${escHtml(c.card_id)}</code></td>
      <td>${escHtml(c.card_label || '—')}</td>
      <td><span class="fw-semibold">${escHtml(c.full_name)}</span> <span class="text-muted small">(${escHtml(c.username)})</span></td>
      <td class="text-muted">${fmtDate(c.enrolled_at)}</td>
      <td class="text-muted">${c.last_used ? fmtDate(c.last_used) : '<span class="text-muted">Never</span>'}</td>
      <td class="text-center">${c.active
        ? '<span class="badge bg-green-lt text-green">Active</span>'
        : '<span class="badge bg-red-lt text-red">Revoked</span>'}</td>
      <td class="text-end">
        <button class="btn btn-sm btn-ghost-${c.active?'warning':'success'}" onclick="toggleCard(${c.id},${c.active})" title="${c.active?'Revoke':'Activate'}">
          <i class="ti ti-${c.active?'slash':'check'}"></i>
        </button>
        <button class="btn btn-sm btn-ghost-danger" onclick="deleteCard(${c.id},'${escHtml(c.card_id)}')" title="Delete">
          <i class="ti ti-trash"></i>
        </button>
      </td>
    </tr>`).join('');
}

function showCardModal() { cardModal.show(); }

async function toggleCard(id, active) {
  await fetch(`/api/cards.php?id=${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ active: !active }),
  });
  loadCards();
}

async function deleteCard(id, cardId) {
  if (!confirm(`Remove card "${cardId}"?`)) return;
  const r = await fetch(`/api/cards.php?id=${id}`, { method: 'DELETE' });
  if (r.ok) loadCards(); else alert('Delete failed.');
}

async function saveCard() {
  const cardId = document.getElementById('cCardId').value.trim().toUpperCase();
  const userId = document.getElementById('cUserId').value;
  const label  = document.getElementById('cLabel').value.trim();
  if (!cardId || !userId) { alert('Card ID and User are required.'); return; }

  const r = await fetch('/api/cards.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card_id: cardId, user_id: parseInt(userId), card_label: label }),
  });
  if (r.ok) { cardModal.hide(); loadCards(); document.getElementById('cCardId').value = ''; }
  else { const e = await r.json(); alert(e.error || 'Save failed.'); }
}

loadCards();
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
