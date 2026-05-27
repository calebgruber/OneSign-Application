<?php
/**
 * Admin Dashboard - Overview stats and live workstation status
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();

$pageTitle = 'Dashboard';

// Stats
$stats = [];
$stats['users']        = db()->query('SELECT COUNT(*) FROM users WHERE active=1')->fetchColumn();
$stats['cards']        = db()->query('SELECT COUNT(*) FROM cards WHERE active=1')->fetchColumn();
$stats['workstations'] = db()->query('SELECT COUNT(*) FROM workstations')->fetchColumn();
$stats['online']       = db()->query("SELECT COUNT(*) FROM workstations WHERE status='online'")->fetchColumn();
$stats['today_logins'] = db()->query("SELECT COUNT(*) FROM audit_log WHERE event_type='card_auth_success' AND DATE(created_at)=CURDATE()")->fetchColumn();
$stats['today_fails']  = db()->query("SELECT COUNT(*) FROM audit_log WHERE event_type IN ('card_not_found','user_disabled') AND DATE(created_at)=CURDATE()")->fetchColumn();

// Recent events
$recent = db()->query("SELECT a.event_type, a.card_id, a.workstation, a.success, a.created_at, u.full_name
    FROM audit_log a LEFT JOIN users u ON a.user_id=u.id
    ORDER BY a.created_at DESC LIMIT 10")->fetchAll();

// Live workstations
$workstations = db()->query("SELECT w.hostname, w.ip_address, w.status, w.last_heartbeat, w.agent_version, u.full_name AS current_user
    FROM workstations w LEFT JOIN users u ON w.current_user_id=u.id ORDER BY w.last_heartbeat DESC")->fetchAll();

include __DIR__ . '/../includes/header.php';
?>

<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <h4 class="fw-bold mb-0">Dashboard</h4>
        <p class="text-muted small mb-0">OneSign deployment overview</p>
    </div>
    <span class="badge bg-success-subtle text-success border border-success-subtle">
        <span class="onesign-dot online me-1"></span>Live
    </span>
</div>

<!-- Stats Cards -->
<div class="row g-3 mb-4">
    <div class="col-6 col-xl-2">
        <div class="card onesign-stat-card border-0 shadow-sm h-100">
            <div class="card-body text-center py-3">
                <div class="onesign-stat-icon bg-primary-subtle text-primary rounded-circle mb-2"><i class="bi bi-people-fill"></i></div>
                <div class="fs-3 fw-bold"><?= (int)$stats['users'] ?></div>
                <div class="text-muted small">Active Users</div>
            </div>
        </div>
    </div>
    <div class="col-6 col-xl-2">
        <div class="card onesign-stat-card border-0 shadow-sm h-100">
            <div class="card-body text-center py-3">
                <div class="onesign-stat-icon bg-success-subtle text-success rounded-circle mb-2"><i class="bi bi-credit-card-fill"></i></div>
                <div class="fs-3 fw-bold"><?= (int)$stats['cards'] ?></div>
                <div class="text-muted small">Enrolled Cards</div>
            </div>
        </div>
    </div>
    <div class="col-6 col-xl-2">
        <div class="card onesign-stat-card border-0 shadow-sm h-100">
            <div class="card-body text-center py-3">
                <div class="onesign-stat-icon bg-info-subtle text-info rounded-circle mb-2"><i class="bi bi-pc-display"></i></div>
                <div class="fs-3 fw-bold"><?= (int)$stats['workstations'] ?></div>
                <div class="text-muted small">Workstations</div>
            </div>
        </div>
    </div>
    <div class="col-6 col-xl-2">
        <div class="card onesign-stat-card border-0 shadow-sm h-100">
            <div class="card-body text-center py-3">
                <div class="onesign-stat-icon bg-success-subtle text-success rounded-circle mb-2"><i class="bi bi-wifi"></i></div>
                <div class="fs-3 fw-bold"><?= (int)$stats['online'] ?></div>
                <div class="text-muted small">Online Now</div>
            </div>
        </div>
    </div>
    <div class="col-6 col-xl-2">
        <div class="card onesign-stat-card border-0 shadow-sm h-100">
            <div class="card-body text-center py-3">
                <div class="onesign-stat-icon bg-primary-subtle text-primary rounded-circle mb-2"><i class="bi bi-box-arrow-in-right"></i></div>
                <div class="fs-3 fw-bold"><?= (int)$stats['today_logins'] ?></div>
                <div class="text-muted small">Logins Today</div>
            </div>
        </div>
    </div>
    <div class="col-6 col-xl-2">
        <div class="card onesign-stat-card border-0 shadow-sm h-100">
            <div class="card-body text-center py-3">
                <div class="onesign-stat-icon bg-danger-subtle text-danger rounded-circle mb-2"><i class="bi bi-shield-exclamation"></i></div>
                <div class="fs-3 fw-bold"><?= (int)$stats['today_fails'] ?></div>
                <div class="text-muted small">Failed Today</div>
            </div>
        </div>
    </div>
</div>

<div class="row g-3">
    <!-- Live Workstations -->
    <div class="col-lg-7">
        <div class="card border-0 shadow-sm">
            <div class="card-header bg-white border-0 pt-3 pb-0">
                <h6 class="fw-semibold mb-0"><i class="bi bi-pc-display me-2 text-primary"></i>Live Workstations</h6>
            </div>
            <div class="card-body p-0">
                <div class="table-responsive">
                    <table class="table table-hover mb-0 align-middle small">
                        <thead class="table-light">
                            <tr>
                                <th class="px-3">Hostname</th>
                                <th>Status</th>
                                <th>Current User</th>
                                <th>Last Seen</th>
                                <th>Agent</th>
                            </tr>
                        </thead>
                        <tbody>
                        <?php if (!$workstations): ?>
                            <tr><td colspan="5" class="text-center text-muted py-4">No workstations registered yet.</td></tr>
                        <?php endif; ?>
                        <?php foreach ($workstations as $ws): ?>
                            <tr>
                                <td class="px-3 fw-semibold"><?= htmlspecialchars($ws['hostname']) ?></td>
                                <td>
                                    <?php
                                    $badgeClass = match($ws['status']) {
                                        'online'  => 'bg-success',
                                        'locked'  => 'bg-warning text-dark',
                                        default   => 'bg-secondary',
                                    };
                                    ?>
                                    <span class="badge <?= $badgeClass ?>"><?= htmlspecialchars($ws['status']) ?></span>
                                </td>
                                <td><?= htmlspecialchars($ws['current_user'] ?? '—') ?></td>
                                <td class="text-muted"><?= $ws['last_heartbeat'] ? date('H:i:s', strtotime($ws['last_heartbeat'])) : '—' ?></td>
                                <td class="text-muted"><?= htmlspecialchars($ws['agent_version'] ?? '—') ?></td>
                            </tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- Recent Events -->
    <div class="col-lg-5">
        <div class="card border-0 shadow-sm">
            <div class="card-header bg-white border-0 pt-3 pb-0">
                <h6 class="fw-semibold mb-0"><i class="bi bi-activity me-2 text-primary"></i>Recent Activity</h6>
            </div>
            <div class="card-body p-0">
                <ul class="list-group list-group-flush">
                <?php if (!$recent): ?>
                    <li class="list-group-item text-center text-muted py-4 small">No events yet.</li>
                <?php endif; ?>
                <?php foreach ($recent as $ev): ?>
                    <li class="list-group-item d-flex align-items-start gap-2 py-2 small">
                        <?php
                        $icon = match($ev['event_type']) {
                            'card_auth_success' => '<i class="bi bi-check-circle-fill text-success mt-1"></i>',
                            'logout'            => '<i class="bi bi-box-arrow-left text-secondary mt-1"></i>',
                            'card_not_found'    => '<i class="bi bi-x-circle-fill text-danger mt-1"></i>',
                            'card_enrolled'     => '<i class="bi bi-plus-circle-fill text-primary mt-1"></i>',
                            default             => '<i class="bi bi-info-circle text-muted mt-1"></i>',
                        };
                        ?>
                        <?= $icon ?>
                        <div class="flex-grow-1 overflow-hidden">
                            <div class="fw-semibold text-truncate"><?= htmlspecialchars($ev['full_name'] ?? $ev['card_id'] ?? 'Unknown') ?></div>
                            <div class="text-muted"><?= htmlspecialchars($ev['event_type']) ?> &middot; <?= htmlspecialchars($ev['workstation'] ?? '—') ?></div>
                        </div>
                        <div class="text-muted text-nowrap"><?= date('H:i', strtotime($ev['created_at'])) ?></div>
                    </li>
                <?php endforeach; ?>
                </ul>
            </div>
        </div>
    </div>
</div>

<?php include __DIR__ . '/../includes/footer.php'; ?>
