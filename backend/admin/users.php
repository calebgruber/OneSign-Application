<?php
/**
 * User Management — Tabler UI with server-side rendered table + modals
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();
$pageTitle = 'Users';
include __DIR__ . '/../includes/header.php';
?>

<!-- Page header -->
<div class="page-header d-print-none">
  <div class="container-xl">
    <div class="row g-2 align-items-center">
      <div class="col">
        <h2 class="page-title">Users</h2>
        <div class="text-muted mt-1">Manage Windows users enrolled in OneSign</div>
      </div>
      <div class="col-auto ms-auto">
        <button class="btn btn-primary" onclick="showUserModal()">
          <i class="ti ti-user-plus me-1"></i>Add User
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
          <input type="text" class="form-control" id="userSearch" placeholder="Search…" oninput="filterTable('users-tbody', this.value)">
          <span class="input-group-text"><i class="ti ti-search"></i></span>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table table-vcenter card-table">
          <thead>
            <tr>
              <th>Full Name</th>
              <th>Username</th>
              <th>Department</th>
              <th class="text-center">Cards</th>
              <th class="text-center">Status</th>
              <th>Created</th>
              <th class="text-end">Actions</th>
            </tr>
          </thead>
          <tbody id="users-tbody">
            <tr><td colspan="7" class="text-center text-muted py-4">
              <div class="spinner-border spinner-border-sm me-2"></div>Loading…
            </td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<!-- User Modal -->
<div class="modal modal-blur fade" id="userModal" tabindex="-1" role="dialog">
  <div class="modal-dialog modal-lg modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="userModalTitle">Add User</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <input type="hidden" id="userId">
        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label required">Windows Username</label>
            <input type="text" class="form-control" id="uUsername" placeholder="DOMAIN\jsmith or jsmith">
          </div>
          <div class="col-md-6">
            <label class="form-label required">Full Name</label>
            <input type="text" class="form-control" id="uFullName" placeholder="John Smith">
          </div>
          <div class="col-md-6">
            <label class="form-label">Email</label>
            <input type="email" class="form-control" id="uEmail" placeholder="jsmith@company.com">
          </div>
          <div class="col-md-6">
            <label class="form-label">Department</label>
            <input type="text" class="form-control" id="uDept" placeholder="Nursing, IT, etc.">
          </div>
          <div class="col-md-6">
            <label class="form-label">Windows Domain</label>
            <input type="text" class="form-control" id="uDomain" placeholder="HOSPITAL">
          </div>
          <div class="col-md-6">
            <label class="form-label">
              Windows Password
              <span class="form-label-description text-muted">(stored encrypted)</span>
            </label>
            <div class="input-group input-group-flat">
              <input type="password" class="form-control" id="uPassword" placeholder="Leave blank to keep existing">
              <span class="input-group-text">
                <a href="#" onclick="togglePw('uPassword');return false" class="link-secondary" title="Show password">
                  <i class="ti ti-eye"></i>
                </a>
              </span>
            </div>
          </div>
          <div class="col-12">
            <label class="form-check form-switch">
              <input class="form-check-input" type="checkbox" id="uActive" checked>
              <span class="form-check-label">Account Active</span>
            </label>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-link link-secondary me-auto" data-bs-dismiss="modal">Cancel</button>
        <button class="btn btn-primary" onclick="saveUser()">
          <i class="ti ti-device-floppy me-1"></i>Save User
        </button>
      </div>
    </div>
  </div>
</div>

<script>
const userModal = createModalController('userModal');
let usersData = [];

async function loadUsers() {
  const res = await fetch('../api/users.php');
  usersData  = await res.json();
  renderUsers(usersData);
}

function renderUsers(data) {
  const tbody = document.getElementById('users-tbody');
  if (!data.length) { tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">No users found.</td></tr>'; return; }
  tbody.innerHTML = data.map(u => `
    <tr data-search="${escHtml((u.full_name+' '+u.username+' '+(u.department||'')).toLowerCase())}">
      <td><div class="d-flex align-items-center gap-2">
        <span class="avatar avatar-sm bg-blue-lt text-blue">${escHtml(u.full_name.charAt(0))}</span>
        <span class="fw-semibold">${escHtml(u.full_name)}</span>
      </div></td>
      <td class="text-muted"><code>${escHtml(u.username)}</code></td>
      <td>${escHtml(u.department || '—')}</td>
      <td class="text-center"><span class="badge bg-blue-lt text-blue">${u.card_count}</span></td>
      <td class="text-center">${u.active
        ? '<span class="badge bg-green-lt text-green">Active</span>'
        : '<span class="badge bg-red-lt text-red">Disabled</span>'}</td>
      <td class="text-muted">${fmtDate(u.created_at)}</td>
      <td class="text-end">
        <button class="btn btn-sm btn-ghost-primary" onclick="editUser(${u.id})" title="Edit"><i class="ti ti-pencil"></i></button>
        <button class="btn btn-sm btn-ghost-danger"  onclick="deleteUser(${u.id}, '${escHtml(u.full_name)}')" title="Delete"><i class="ti ti-trash"></i></button>
      </td>
    </tr>`).join('');
}

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

async function editUser(id) {
  const r = await fetch(`../api/users.php?id=${id}`);
  showUserModal(await r.json());
}

async function deleteUser(id, name) {
  if (!confirm(`Delete user "${name}"? This will also remove all their enrolled cards.`)) return;
  const r = await fetch(`../api/users.php?id=${id}`, { method: 'DELETE' });
  if (r.ok) loadUsers(); else alert('Delete failed.');
}

async function saveUser() {
  const id   = document.getElementById('userId').value;
  const body = {
    username:       document.getElementById('uUsername').value.trim(),
    full_name:      document.getElementById('uFullName').value.trim(),
    email:          document.getElementById('uEmail').value.trim(),
    department:     document.getElementById('uDept').value.trim(),
    windows_domain: document.getElementById('uDomain').value.trim(),
    active:         document.getElementById('uActive').checked,
  };
  const pw = document.getElementById('uPassword').value;
  if (pw) body.windows_password = pw;
  if (!body.username || !body.full_name) { alert('Username and Full Name are required.'); return; }

  const r = await fetch(id ? `../api/users.php?id=${id}` : '../api/users.php', {
    method: id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (r.ok) { userModal.hide(); loadUsers(); }
  else { const e = await r.json(); alert(e.error || 'Save failed.'); }
}

loadUsers();
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
