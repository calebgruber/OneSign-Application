<?php
/**
 * Audit Log - Tabulator view
 */
require_once __DIR__ . '/../includes/auth_check.php';
requireAdminLogin();
$pageTitle = 'Audit Log';
include __DIR__ . '/../includes/header.php';
?>

<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <h4 class="fw-bold mb-0">Audit Log</h4>
        <p class="text-muted small mb-0">Full history of OneSign events</p>
    </div>
    <button class="btn btn-outline-secondary btn-sm" onclick="table.clearFilter(); table.setData()">
        <i class="bi bi-arrow-clockwise me-1"></i>Refresh
    </button>
</div>

<div class="card border-0 shadow-sm">
    <div class="card-body">
        <div id="audit-table"></div>
    </div>
</div>

<script>
const table = new Tabulator('#audit-table', {
    ajaxURL: '/api/audit.php?limit=500',
    layout: 'fitColumns',
    pagination: 'local',
    paginationSize: 20,
    placeholder: 'No events found.',
    initialSort: [{ column: 'created_at', dir: 'desc' }],
    columns: [
        { title: 'Time', field: 'created_at', sorter: 'datetime', width: 160,
          formatter: (c) => fmtDate(c.getValue(), true) },
        { title: 'Event', field: 'event_type', sorter: 'string', widthGrow: 1.5,
          formatter: (c) => {
            const ev = c.getValue();
            const badgeClass = ev.includes('success') || ev.includes('enrolled') ? 'bg-success'
                : ev.includes('fail') || ev.includes('not_found') || ev.includes('disabled') ? 'bg-danger'
                : ev === 'logout' ? 'bg-secondary' : 'bg-primary';
            return `<span class="badge ${badgeClass}">${escHtml(ev.replace(/_/g,' '))}</span>`;
          }},
        { title: 'User', field: 'full_name', sorter: 'string', widthGrow: 1.5,
          formatter: (c) => escHtml(c.getValue() || '—') },
        { title: 'Card ID', field: 'card_id', sorter: 'string',
          formatter: (c) => c.getValue() ? `<code>${escHtml(c.getValue())}</code>` : '—' },
        { title: 'Workstation', field: 'workstation', sorter: 'string',
          formatter: (c) => escHtml(c.getValue() || '—') },
        { title: 'IP', field: 'ip_address', sorter: 'string', width: 130 },
        { title: 'Result', field: 'success', hozAlign: 'center', width: 90,
          formatter: (c) => c.getValue()
            ? '<span class="badge bg-success">OK</span>'
            : '<span class="badge bg-danger">FAIL</span>' },
        { title: 'Details', field: 'details', sorter: 'string', widthGrow: 2,
          formatter: (c) => `<span class="text-muted small">${escHtml(c.getValue() || '')}</span>` },
    ],
});
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>
