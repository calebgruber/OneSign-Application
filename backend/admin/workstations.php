<?php
/**
 * Workstations — Tabler UI
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();
$pageTitle = 'Workstations';
include __DIR__ . '/../includes/header.php';
?>

<div class="page-header d-print-none">
  <div class="container-xl">
    <div class="row g-2 align-items-center">
      <div class="col">
        <h2 class="page-title">Workstations</h2>
        <div class="text-muted mt-1">PCs running the OneSign agent</div>
      </div>
    </div>
  </div>
</div>

<div class="page-body">
  <div class="container-xl">

    <!-- API Keys card -->
    <div class="card mb-4">
      <div class="card-header">
        <h3 class="card-title"><i class="ti ti-key me-2 text-blue"></i>Agent API Keys</h3>
        <div class="card-options">
          <button class="btn btn-sm btn-primary" onclick="createApiKey()">
            <i class="ti ti-plus me-1"></i>Generate Key
          </button>
        </div>
      </div>
      <div class="card-body pb-0">
        <p class="text-muted small mb-3">Copy a key into <code>config.ini</code> on each workstation running the agent.</p>
      </div>
      <div class="table-responsive">
        <table class="table table-vcenter card-table">
          <thead>
            <tr>
              <th>Label</th>
              <th>API Key</th>
              <th>Workstation</th>
              <th>Last Used</th>
              <th class="text-center">Status</th>
              <th class="text-end">Actions</th>
            </tr>
          </thead>
          <tbody id="keys-tbody">
            <tr><td colspan="6" class="text-center text-muted py-3">
              <div class="spinner-border spinner-border-sm me-2"></div>Loading…
            </td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Workstations card -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title"><i class="ti ti-device-desktop me-2 text-blue"></i>Registered Workstations</h3>
        <div class="card-options">
          <button class="btn btn-sm btn-ghost-secondary" onclick="loadWorkstations()">
            <i class="ti ti-refresh"></i>
          </button>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table table-vcenter card-table">
          <thead>
            <tr>
              <th>Hostname</th>
              <th>IP Address</th>
              <th class="text-center">Status</th>
              <th>Current User</th>
              <th>OS</th>
              <th>Agent</th>
              <th>Last Heartbeat</th>
            </tr>
          </thead>
          <tbody id="ws-tbody">
            <tr><td colspan="7" class="text-center text-muted py-4">
              <div class="spinner-border spinner-border-sm me-2"></div>Loading…
            </td></tr>
          </tbody>
        </table>
      </div>
    </div>

  </div>
</div>

<script>
async function loadApiKeys() {
  const res  = await fetch('../api/apikeys.php');
  const data = await res.json();
  const tbody = document.getElementById('keys-tbody');
  if (!data.length) { tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-3">No API keys. Generate one above.</td></tr>'; return; }
  tbody.innerHTML = data.map(k => `
    <tr>
      <td class="fw-semibold">${escHtml(k.label)}</td>
      <td><code class="user-select-all small">${escHtml(k.api_key)}</code></td>
      <td>${escHtml(k.workstation || 'Any')}</td>
      <td class="text-muted">${k.last_used ? fmtDate(k.last_used, true) : '<span class="text-muted">Never</span>'}</td>
      <td class="text-center">${k.active
        ? '<span class="badge bg-green-lt text-green">Active</span>'
        : '<span class="badge bg-red-lt text-red">Revoked</span>'}</td>
      <td class="text-end">
        <button class="btn btn-sm btn-ghost-danger" onclick="deleteKey(${k.id})" title="Revoke">
          <i class="ti ti-trash"></i>
        </button>
      </td>
    </tr>`).join('');
}

async function loadWorkstations() {
  const res  = await fetch('../api/workstations.php');
  const data = await res.json();
  const tbody = document.getElementById('ws-tbody');
  if (!data.length) { tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">No workstations registered yet.</td></tr>'; return; }
  tbody.innerHTML = data.map(w => {
    const cls = w.status === 'online' ? 'bg-green' : w.status === 'locked' ? 'bg-yellow text-yellow-fg' : 'bg-secondary';
    return `
      <tr>
        <td class="fw-semibold">${escHtml(w.hostname)}</td>
        <td class="text-muted">${escHtml(w.ip_address || '—')}</td>
        <td class="text-center"><span class="badge ${cls}">${w.status}</span></td>
        <td>${escHtml(w.current_user || '—')}</td>
        <td class="text-muted small">${escHtml(w.os_version || '—')}</td>
        <td class="text-muted">${escHtml(w.agent_version || '—')}</td>
        <td class="text-muted">${w.last_heartbeat ? fmtDate(w.last_heartbeat, true) : '—'}</td>
      </tr>`;
  }).join('');
}

async function createApiKey() {
  const label = prompt('Label for this API key (e.g. workstation name):');
  if (!label) return;
  const r = await fetch('../api/apikeys.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label }),
  });
  if (r.ok) loadApiKeys(); else alert('Failed to create key.');
}

async function deleteKey(id) {
  if (!confirm('Revoke this API key? Agents using it will stop working.')) return;
  await fetch(`../api/apikeys.php?id=${id}`, { method: 'DELETE' });
  loadApiKeys();
}

loadApiKeys();
loadWorkstations();
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
