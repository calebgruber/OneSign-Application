<?php
/**
 * Workstations - live status with Tabulator
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();
$pageTitle = 'Workstations';
include __DIR__ . '/../includes/header.php';
?>

<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <h4 class="fw-bold mb-0">Workstations</h4>
        <p class="text-muted small mb-0">PCs running the OneSign agent</p>
    </div>
</div>

<!-- API Key section -->
<div class="card border-0 shadow-sm mb-4">
    <div class="card-header bg-white border-0 pt-3 pb-0">
        <h6 class="fw-semibold"><i class="bi bi-key me-2 text-primary"></i>Agent API Keys</h6>
    </div>
    <div class="card-body">
        <p class="text-muted small">Copy an API key into the agent <code>config.ini</code> on each workstation.</p>
        <div id="apikeys-table" class="mb-3"></div>
        <button class="btn btn-sm btn-outline-primary" onclick="createApiKey()"><i class="bi bi-plus me-1"></i>Generate New Key</button>
    </div>
</div>

<!-- Workstations table -->
<div class="card border-0 shadow-sm">
    <div class="card-body">
        <div id="ws-table"></div>
    </div>
</div>

<script>
const wsTable = new Tabulator('#ws-table', {
    ajaxURL: '/api/workstations.php',
    layout: 'fitColumns',
    pagination: 'local',
    paginationSize: 20,
    placeholder: 'No workstations registered.',
    columns: [
        { title: 'Hostname', field: 'hostname', sorter: 'string', widthGrow: 1.5, formatter: (c) => `<strong>${escHtml(c.getValue())}</strong>` },
        { title: 'IP', field: 'ip_address', sorter: 'string' },
        { title: 'Status', field: 'status', hozAlign: 'center', width: 100,
          formatter: (c) => {
            const s = c.getValue();
            const cls = s === 'online' ? 'bg-success' : s === 'locked' ? 'bg-warning text-dark' : 'bg-secondary';
            return `<span class="badge ${cls}">${s}</span>`;
          }},
        { title: 'Current User', field: 'current_user', widthGrow: 1.5, formatter: (c) => escHtml(c.getValue() || '—') },
        { title: 'OS', field: 'os_version', widthGrow: 2, formatter: (c) => `<span class="text-muted small">${escHtml(c.getValue() || '—')}</span>` },
        { title: 'Agent', field: 'agent_version', width: 100 },
        { title: 'Last Heartbeat', field: 'last_heartbeat', sorter: 'datetime', formatter: (c) => fmtDate(c.getValue(), true) },
    ],
});

const keyTable = new Tabulator('#apikeys-table', {
    ajaxURL: '/api/apikeys.php',
    layout: 'fitColumns',
    placeholder: 'No API keys yet.',
    columns: [
        { title: 'Label', field: 'label', sorter: 'string', widthGrow: 1.5 },
        { title: 'API Key', field: 'api_key', widthGrow: 3,
          formatter: (c) => `<code class="user-select-all small">${escHtml(c.getValue())}</code>` },
        { title: 'Workstation', field: 'workstation', formatter: (c) => escHtml(c.getValue() || 'Any') },
        { title: 'Last Used', field: 'last_used', sorter: 'datetime', formatter: (c) => c.getValue() ? fmtDate(c.getValue(), true) : '<span class="text-muted">Never</span>' },
        { title: 'Status', field: 'active', hozAlign: 'center', width: 90,
          formatter: (c) => c.getValue()
            ? '<span class="badge bg-success">Active</span>'
            : '<span class="badge bg-danger">Revoked</span>' },
        { title: '', width: 80, headerSort: false,
          formatter: () => '<button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button>',
          cellClick: async (e, cell) => {
            if (!confirm('Revoke this API key?')) return;
            await fetch(`/api/apikeys.php?id=${cell.getRow().getData().id}`, { method: 'DELETE' });
            keyTable.setData();
          }
        },
    ],
});

async function createApiKey() {
    const label = prompt('Label for this API key (e.g. workstation name):');
    if (!label) return;
    const r = await fetch('/api/apikeys.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label }),
    });
    if (r.ok) keyTable.setData(); else alert('Failed to create key.');
}
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
