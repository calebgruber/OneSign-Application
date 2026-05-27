<?php
/**
 * Card Management - Tabulator-powered CRUD
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();
$pageTitle = 'Cards';
// Fetch users for dropdown
$allUsers = db()->query('SELECT id, username, full_name FROM users WHERE active=1 ORDER BY full_name')->fetchAll();
include __DIR__ . '/../includes/header.php';
?>

<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <h4 class="fw-bold mb-0">Enrolled Cards</h4>
        <p class="text-muted small mb-0">Manage RFID/proximity cards linked to Windows users</p>
    </div>
    <button class="btn btn-primary" onclick="showCardModal()">
        <i class="bi bi-credit-card-2-front me-1"></i>Add Card
    </button>
</div>

<div class="card border-0 shadow-sm">
    <div class="card-body">
        <div id="cards-table"></div>
    </div>
</div>

<!-- Card Modal -->
<div class="modal fade" id="cardModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header onesign-modal-header">
                <h5 class="modal-title text-white">Add Card</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body p-4">
                <div class="mb-3">
                    <label class="form-label fw-semibold">Card ID (Hex) *</label>
                    <input type="text" class="form-control font-monospace" id="cCardId" placeholder="e.g. A1B2C3D4">
                    <div class="form-text">Tap a card on a pcProx reader to see the ID, or use the Enroll page.</div>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Assign to User *</label>
                    <select class="form-select" id="cUserId">
                        <option value="">— Select User —</option>
                        <?php foreach ($allUsers as $u): ?>
                        <option value="<?= $u['id'] ?>"><?= htmlspecialchars($u['full_name']) ?> (<?= htmlspecialchars($u['username']) ?>)</option>
                        <?php endforeach; ?>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Label</label>
                    <input type="text" class="form-control" id="cLabel" placeholder="e.g. ID Badge">
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-primary" onclick="saveCard()"><i class="bi bi-save me-1"></i>Save Card</button>
            </div>
        </div>
    </div>
</div>

<script>
const cardModal = new bootstrap.Modal(document.getElementById('cardModal'));

const table = new Tabulator('#cards-table', {
    ajaxURL: '/api/cards.php',
    layout: 'fitColumns',
    pagination: 'local',
    paginationSize: 15,
    placeholder: 'No cards enrolled.',
    columns: [
        { title: 'Card ID', field: 'card_id', sorter: 'string', formatter: (c) => `<code>${escHtml(c.getValue())}</code>` },
        { title: 'Label', field: 'card_label', sorter: 'string' },
        { title: 'User', field: 'full_name', sorter: 'string', widthGrow: 1.5,
          formatter: (c, row) => `<strong>${escHtml(c.getValue())}</strong> <span class="text-muted">(${escHtml(row.getData().username)})</span>` },
        { title: 'Enrolled', field: 'enrolled_at', sorter: 'datetime', formatter: (c) => fmtDate(c.getValue()) },
        { title: 'Last Used', field: 'last_used', sorter: 'datetime', formatter: (c) => c.getValue() ? fmtDate(c.getValue()) : '<span class="text-muted">Never</span>' },
        { title: 'Status', field: 'active', hozAlign: 'center', width: 100,
          formatter: (c) => c.getValue()
            ? '<span class="badge bg-success">Active</span>'
            : '<span class="badge bg-danger">Revoked</span>' },
        { title: 'Actions', hozAlign: 'center', width: 140, headerSort: false,
          formatter: (c) => {
            const d = c.getRow().getData();
            return `<button class="btn btn-sm ${d.active ? 'btn-outline-warning' : 'btn-outline-success'} me-1" title="${d.active ? 'Revoke' : 'Activate'}">
                      <i class="bi bi-${d.active ? 'slash-circle' : 'check-circle'}"></i></button>
                    <button class="btn btn-sm btn-outline-danger" title="Delete"><i class="bi bi-trash"></i></button>`;
          },
          cellClick: (e, cell) => {
            const row = cell.getRow().getData();
            if (e.target.closest('.btn-outline-warning') || e.target.closest('.btn-outline-success')) toggleCard(row);
            if (e.target.closest('.btn-outline-danger')) deleteCard(row);
          }
        },
    ],
});

function showCardModal() { cardModal.show(); }

async function toggleCard(row) {
    const r = await fetch(`/api/cards.php?id=${row.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: !row.active }),
    });
    if (r.ok) table.setData();
}

async function deleteCard(row) {
    if (!confirm(`Remove card "${row.card_id}"?`)) return;
    const r = await fetch(`/api/cards.php?id=${row.id}`, { method: 'DELETE' });
    if (r.ok) table.setData(); else alert('Delete failed.');
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
    if (r.ok) { cardModal.hide(); table.setData(); document.getElementById('cCardId').value = ''; }
    else { const e = await r.json(); alert(e.error || 'Save failed.'); }
}
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
