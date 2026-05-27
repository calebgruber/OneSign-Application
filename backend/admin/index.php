<?php
/**
 * Admin Dashboard - Overview stats and live workstation status
 */
require_once __DIR__ . '/../includes/auth_check.php';
require_once __DIR__ . '/../includes/db.php';
requireAdminLogin();

$pageTitle = 'Dashboard';

$stats = [];
$stats['users']        = db()->query('SELECT COUNT(*) FROM users WHERE active=1')->fetchColumn();
$stats['cards']        = db()->query('SELECT COUNT(*) FROM cards WHERE active=1')->fetchColumn();
$stats['workstations'] = db()->query('SELECT COUNT(*) FROM workstations')->fetchColumn();
$stats['online']       = db()->query("SELECT COUNT(*) FROM workstations WHERE status='online'")->fetchColumn();
$stats['today_logins'] = db()->query("SELECT COUNT(*) FROM audit_log WHERE event_type='card_auth_success' AND DATE(created_at)=CURDATE()")->fetchColumn();
$stats['today_fails']  = db()->query("SELECT COUNT(*) FROM audit_log WHERE event_type IN ('card_not_found','user_disabled') AND DATE(created_at)=CURDATE()")->fetchColumn();

$recent = db()->query("SELECT a.event_type, a.card_id, a.workstation, a.success, a.created_at, u.full_name
    FROM audit_log a LEFT JOIN users u ON a.user_id=u.id
    ORDER BY a.created_at DESC LIMIT 10")->fetchAll();

$workstations = db()->query("SELECT w.hostname, w.ip_address, w.status, w.last_heartbeat, w.agent_version, u.full_name AS current_user
    FROM workstations w LEFT JOIN users u ON w.current_user_id=u.id ORDER BY w.last_heartbeat DESC")->fetchAll();

include __DIR__ . '/../includes/header.php';
?>

<!-- Page header -->
<div class="page-header d-print-none">
  <div class="container-xl">
    <div class="row g-2 align-items-center">
      <div class="col">
        <h2 class="page-title">Dashboard</h2>
        <div class="text-muted mt-1">OneSign deployment overview</div>
      </div>
      <div class="col-auto ms-auto">
        <span class="badge bg-green-lt"><span class="onesign-dot me-1"></span>Live</span>
      </div>
    </div>
  </div>
</div>

<div class="page-body">
  <div class="container-xl">

    <!-- Stat Cards -->
    <div class="row row-deck row-cards mb-4">
      <?php
      $statItems = [
        ['icon'=>'ti-users',             'color'=>'blue',   'value'=>$stats['users'],        'label'=>'Active Users'],
        ['icon'=>'ti-id-badge',          'color'=>'green',  'value'=>$stats['cards'],        'label'=>'Enrolled Cards'],
        ['icon'=>'ti-device-desktop',    'color'=>'cyan',   'value'=>$stats['workstations'], 'label'=>'Workstations'],
        ['icon'=>'ti-wifi',              'color'=>'teal',   'value'=>$stats['online'],       'label'=>'Online Now'],
        ['icon'=>'ti-login',             'color'=>'indigo', 'value'=>$stats['today_logins'], 'label'=>'Logins Today'],
        ['icon'=>'ti-shield-exclamation','color'=>'red',    'value'=>$stats['today_fails'],  'label'=>'Failed Today'],
      ];
      foreach ($statItems as $si): ?>
      <div class="col-6 col-xl-2">
        <div class="card card-sm">
          <div class="card-body">
            <div class="row align-items-center">
              <div class="col-auto">
                <span class="avatar bg-<?= $si['color'] ?>-lt text-<?= $si['color'] ?>">
                  <i class="ti <?= $si['icon'] ?>"></i>
                </span>
              </div>
              <div class="col">
                <div class="font-weight-medium"><?= (int)$si['value'] ?></div>
                <div class="text-muted small"><?= $si['label'] ?></div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <?php endforeach; ?>
    </div>

    <div class="row row-deck row-cards">
      <!-- Live Workstations -->
      <div class="col-lg-7">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="ti ti-device-desktop me-2 text-blue"></i>Live Workstations</h3>
          </div>
          <div class="table-responsive">
            <table class="table table-vcenter card-table">
              <thead>
                <tr>
                  <th>Hostname</th>
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
              <?php foreach ($workstations as $ws):
                $badgeCls = match($ws['status']) {
                  'online' => 'bg-green',
                  'locked' => 'bg-yellow text-yellow-fg',
                  default  => 'bg-secondary',
                };
              ?>
                <tr>
                  <td class="fw-semibold"><?= htmlspecialchars($ws['hostname']) ?></td>
                  <td><span class="badge <?= $badgeCls ?>"><?= htmlspecialchars($ws['status']) ?></span></td>
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

      <!-- Recent Activity -->
      <div class="col-lg-5">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="ti ti-activity me-2 text-blue"></i>Recent Activity</h3>
          </div>
          <div class="list-group list-group-flush overflow-auto" style="max-height:420px">
          <?php if (!$recent): ?>
            <div class="list-group-item text-center text-muted py-4 small">No events yet.</div>
          <?php endif; ?>
          <?php foreach ($recent as $ev):
            [$icon, $cls] = match($ev['event_type']) {
              'card_auth_success' => ['ti-check',      'text-green'],
              'logout'            => ['ti-logout',     'text-muted'],
              'card_not_found'    => ['ti-x',          'text-red'],
              'card_enrolled'     => ['ti-plus',       'text-blue'],
              default             => ['ti-info-circle','text-muted'],
            };
          ?>
            <div class="list-group-item">
              <div class="row align-items-center">
                <div class="col-auto"><i class="ti <?= $icon ?> <?= $cls ?>"></i></div>
                <div class="col text-truncate">
                  <span class="fw-semibold"><?= htmlspecialchars($ev['full_name'] ?? $ev['card_id'] ?? 'Unknown') ?></span>
                  <div class="d-block text-muted text-truncate small">
                    <?= htmlspecialchars(str_replace('_',' ',$ev['event_type'])) ?>
                    &middot; <?= htmlspecialchars($ev['workstation'] ?? '—') ?>
                  </div>
                </div>
                <div class="col-auto text-muted small"><?= date('H:i', strtotime($ev['created_at'])) ?></div>
              </div>
            </div>
          <?php endforeach; ?>
          </div>
        </div>
      </div>
    </div>

  </div>
</div>

<?php include __DIR__ . '/../includes/footer.php'; ?>
