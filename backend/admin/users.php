<?php
/**
 * User Management - Tabulator-powered CRUD
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();
$pageTitle = 'Users';
include __DIR__ . '/../includes/header.php';
?>

<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <h4 class="fw-bold mb-0">Users</h4>
        <p class="text-muted small mb-0">Manage Windows users enrolled in OneSign</p>
    </div>
    <button class="btn btn-primary" onclick="showUserModal()">
        <i class="bi bi-person-plus me-1"></i>Add User
    </button>
</div>

<div class="card border-0 shadow-sm">
    <div class="card-body">
        <div id="users-table"></div>
    </div>
</div>

<!-- User Modal -->
<div class="modal fade" id="userModal" tabindex="-1">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header onesign-modal-header">
                <h5 class="modal-title text-white" id="userModalTitle">Add User</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body p-4">
                <input type="hidden" id="userId">
                <div class="row g-3">
                    <div class="col-md-6">
                        <label class="form-label fw-semibold">Windows Username *</label>
                        <input type="text" class="form-control" id="uUsername" placeholder="DOMAIN\jsmith or jsmith">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label fw-semibold">Full Name *</label>
                        <input type="text" class="form-control" id="uFullName" placeholder="John Smith">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label fw-semibold">Email</label>
                        <input type="email" class="form-control" id="uEmail" placeholder="jsmith@company.com">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label fw-semibold">Department</label>
                        <input type="text" class="form-control" id="uDept" placeholder="Nursing, IT, etc.">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label fw-semibold">Windows Domain</label>
                        <input type="text" class="form-control" id="uDomain" placeholder="HOSPITAL (optional)">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label fw-semibold">Windows Password
                            <span class="text-muted fw-normal small">(stored encrypted)</span>
                        </label>
                        <div class="input-group">
                            <input type="password" class="form-control" id="uPassword" placeholder="Leave blank to keep existing">
                            <button class="btn btn-outline-secondary" type="button" onclick="togglePw('uPassword')"><i class="bi bi-eye"></i></button>
                        </div>
                    </div>
                    <div class="col-12">
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="uActive" checked>
                            <label class="form-check-label fw-semibold" for="uActive">Account Active</label>
                        </div>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-primary" onclick="saveUser()"><i class="bi bi-save me-1"></i>Save User</button>
            </div>
        </div>
    </div>
</div>

<script>
const userModal = new bootstrap.Modal(document.getElementById('userModal'));

const table = new Tabulator('#users-table', {
    ajaxURL: '/api/users.php',
    layout: 'fitColumns',
    pagination: 'local',
    paginationSize: 15,
    responsiveLayout: 'hide',
    placeholder: 'No users found.',
    columns: [
        { title: 'Full Name', field: 'full_name', sorter: 'string', widthGrow: 2,
          formatter: (cell) => `<strong>${escHtml(cell.getValue())}</strong>` },
        { title: 'Username', field: 'username', sorter: 'string', widthGrow: 1.5 },
        { title: 'Department', field: 'department', sorter: 'string' },
        { title: 'Cards', field: 'card_count', hozAlign: 'center', width: 80,
          formatter: (cell) => `<span class="badge bg-primary-subtle text-primary">${cell.getValue()}</span>` },
        { title: 'Status', field: 'active', hozAlign: 'center', width: 100,
          formatter: (cell) => cell.getValue()
            ? '<span class="badge bg-success">Active</span>'
            : '<span class="badge bg-danger">Disabled</span>' },
        { title: 'Created', field: 'created_at', sorter: 'datetime', widthGrow: 1.2,
          formatter: (cell) => fmtDate(cell.getValue()) },
        { title: 'Actions', hozAlign: 'center', width: 120, headerSort: false,
          formatter: () => `
            <button class="btn btn-sm btn-outline-primary me-1" title="Edit"><i class="bi bi-pencil"></i></button>
            <button class="btn btn-sm btn-outline-danger" title="Delete"><i class="bi bi-trash"></i></button>`,
          cellClick: (e, cell) => {
            const row = cell.getRow().getData();
            if (e.target.closest('.btn-outline-primary')) editUser(row);
            if (e.target.closest('.btn-outline-danger')) deleteUser(row);
          }
        },
    ],
});

function showUserModal(data) {
    document.getElementById('userId').value      = data?.id || '';
    document.getElementById('uUsername').value   = data?.username || '';
    document.getElementById('uFullName').value   = data?.full_name || '';
    document.getElementById('uEmail').value      = data?.email || '';
    document.getElementById('uDept').value       = data?.department || '';
    document.getElementById('uDomain').value     = data?.windows_domain || '';
    document.getElementById('uPassword').value   = '';
    document.getElementById('uActive').checked   = data ? !!data.active : true;
    document.getElementById('uUsername').disabled= !!data?.id;
    document.getElementById('userModalTitle').textContent = data?.id ? 'Edit User' : 'Add User';
    userModal.show();
}

function editUser(row) { showUserModal(row); }

async function deleteUser(row) {
    if (!confirm(`Delete user "${row.full_name}"? This will also remove all their enrolled cards.`)) return;
    const r = await fetch(`/api/users.php?id=${row.id}`, { method: 'DELETE' });
    if (r.ok) { table.setData(); } else { alert('Delete failed.'); }
}

async function saveUser() {
    const id = document.getElementById('userId').value;
    const body = {
        username: document.getElementById('uUsername').value.trim(),
        full_name: document.getElementById('uFullName').value.trim(),
        email: document.getElementById('uEmail').value.trim(),
        department: document.getElementById('uDept').value.trim(),
        windows_domain: document.getElementById('uDomain').value.trim(),
        active: document.getElementById('uActive').checked,
    };
    const pw = document.getElementById('uPassword').value;
    if (pw) body.windows_password = pw;

    if (!body.username || !body.full_name) { alert('Username and Full Name are required.'); return; }

    const method = id ? 'PUT' : 'POST';
    const url    = id ? `/api/users.php?id=${id}` : '/api/users.php';
    const r      = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

    if (r.ok) { userModal.hide(); table.setData(); }
    else      { const e = await r.json(); alert(e.error || 'Save failed.'); }
}

function togglePw(id) {
    const el = document.getElementById(id);
    el.type = el.type === 'password' ? 'text' : 'password';
}
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
