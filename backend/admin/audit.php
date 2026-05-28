<?php
/**
 * Audit Log — Tabler UI table
 */
require_once __DIR__ . '/../includes/auth_check.php';
requireAdminLogin();
$pageTitle = 'Audit Log';
include __DIR__ . '/../includes/header.php';
?>

<div class="page-header d-print-none">
  <div class="container-xl">
    <div class="row g-2 align-items-center">
      <div class="col">
        <h2 class="page-title">Audit Log</h2>
        <div class="text-muted mt-1">Full history of OneSign authentication events</div>
      </div>
      <div class="col-auto ms-auto d-flex gap-2">
        <div class="input-group input-group-sm">
          <input type="text" class="form-control" id="auditSearch" placeholder="Search…" oninput="filterTable('audit-tbody', this.value)">
          <span class="input-group-text"><i class="ti ti-search"></i></span>
        </div>
        <button class="btn btn-sm btn-outline-secondary" onclick="loadAudit()">
          <i class="ti ti-refresh"></i>
        </button>
      </div>
    </div>
  </div>
</div>

<div class="page-body">
  <div class="container-xl">
    <div class="card">
      <div class="table-responsive">
        <table class="table table-vcenter card-table table-sm">
          <thead>
            <tr>
              <th>Time</th>
              <th>Event</th>
              <th>User</th>
              <th>Card ID</th>
              <th>Workstation</th>
              <th>IP</th>
              <th class="text-center">Result</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody id="audit-tbody">
            <tr><td colspan="8" class="text-center text-muted py-4">
              <div class="spinner-border spinner-border-sm me-2"></div>Loading…
            </td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script>
async function loadAudit() {
  const res  = await fetch('../api/audit.php?limit=500');
  const data = await res.json();
  const tbody = document.getElementById('audit-tbody');
  if (!data.length) { tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">No events found.</td></tr>'; return; }

  tbody.innerHTML = data.map(ev => {
    const badgeCls = ev.event_type.includes('success') || ev.event_type.includes('enrolled')
      ? 'onesign-badge-green'
      : ev.event_type.includes('not_found') || ev.event_type.includes('disabled')
        ? 'onesign-badge-red'
        : ev.event_type === 'logout'
          ? 'onesign-badge-gray'
          : 'onesign-badge-blue';
    return `
      <tr data-search="${escHtml(((ev.full_name||'')+(ev.card_id||'')+(ev.workstation||'')+ev.event_type).toLowerCase())}">
        <td class="text-muted small text-nowrap">${fmtDate(ev.created_at, true)}</td>
        <td><span class="badge ${badgeCls}">${escHtml(ev.event_type.replace(/_/g,' '))}</span></td>
        <td>${escHtml(ev.full_name || '—')}</td>
        <td>${ev.card_id ? `<code>${escHtml(ev.card_id)}</code>` : '—'}</td>
        <td>${escHtml(ev.workstation || '—')}</td>
        <td class="text-muted small">${escHtml(ev.ip_address || '')}</td>
        <td class="text-center">${ev.success
          ? '<span class="badge onesign-badge-green">OK</span>'
          : '<span class="badge onesign-badge-red">FAIL</span>'}</td>
        <td class="text-muted small">${escHtml(ev.details || '')}</td>
      </tr>`;
  }).join('');
}

loadAudit();
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
