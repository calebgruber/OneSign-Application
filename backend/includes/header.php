<?php
/**
 * Shared admin header template — Tabler UI
 */
$pageTitle = $pageTitle ?? 'Dashboard';
$adminName = $_SESSION['admin_name'] ?? 'Admin';
$adminRole = $_SESSION['admin_role'] ?? 'admin';
$currentPage = basename($_SERVER['PHP_SELF']);

function navItem(string $href, string $icon, string $label, string $current): string {
    $active = $current === basename($href) ? ' active' : '';
    return '<a class="nav-link' . $active . '" href="' . $href . '">'
         . '<span class="nav-link-icon d-md-none d-lg-inline-block"><i class="ti ' . $icon . '"></i></span>'
         . '<span class="nav-link-title">' . $label . '</span>'
         . '</a>';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>OneSign &mdash; <?= htmlspecialchars($pageTitle) ?></title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0-beta20/dist/css/tabler.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.11.0/dist/tabler-icons.min.css">
  <link rel="stylesheet" href="/assets/css/onesign.css">
</head>
<body class="antialiased">
<div class="wrapper">

<!-- Vertical Navbar / Sidebar -->
<aside class="navbar navbar-vertical navbar-expand-lg onesign-sidebar" data-bs-theme="dark">
  <div class="container-fluid">
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#sidebar-menu">
      <span class="navbar-toggler-icon"></span>
    </button>

    <!-- Brand -->
    <h1 class="navbar-brand navbar-brand-autodark">
      <a href="/admin/index.php" class="d-flex align-items-center gap-2 text-white text-decoration-none">
        <img src="/assets/img/logo.svg" height="32" alt="OneSign" class="navbar-brand-image">
        <span class="fw-bold fs-5">OneSign</span>
      </a>
    </h1>

    <!-- User pill (mobile) -->
    <div class="navbar-nav flex-row d-lg-none">
      <div class="nav-item dropdown">
        <a href="#" class="nav-link d-flex lh-1 text-reset p-0" data-bs-toggle="dropdown">
          <div class="avatar avatar-sm">
            <span class="avatar-initials bg-primary text-white"><?= strtoupper(substr($adminName,0,1)) ?></span>
          </div>
        </a>
        <div class="dropdown-menu dropdown-menu-end">
          <a class="dropdown-item" href="/admin/logout.php"><i class="ti ti-logout me-2"></i>Sign out</a>
        </div>
      </div>
    </div>

    <!-- Nav links -->
    <div class="collapse navbar-collapse" id="sidebar-menu">
      <ul class="navbar-nav pt-lg-3">
        <li class="nav-item"><?= navItem('/admin/index.php',        'ti-dashboard',       'Dashboard',    $currentPage) ?></li>
        <li class="nav-item"><?= navItem('/admin/users.php',        'ti-users',           'Users',        $currentPage) ?></li>
        <li class="nav-item"><?= navItem('/admin/cards.php',        'ti-id-badge',        'Cards',        $currentPage) ?></li>
        <li class="nav-item"><?= navItem('/admin/enroll.php',       'ti-user-plus',       'Enroll',       $currentPage) ?></li>
        <li class="nav-item"><?= navItem('/admin/audit.php',        'ti-file-analytics',  'Audit Log',    $currentPage) ?></li>
        <li class="nav-item"><?= navItem('/admin/workstations.php', 'ti-device-desktop',  'Workstations', $currentPage) ?></li>
        <li class="nav-item mt-2 border-top pt-2"><?= navItem('/admin/settings.php', 'ti-settings', 'Settings', $currentPage) ?></li>
      </ul>

      <!-- Bottom user info (desktop) -->
      <div class="mt-auto d-none d-lg-block pb-3">
        <div class="d-flex align-items-center gap-2 px-2">
          <div class="avatar avatar-sm">
            <span class="avatar-initials bg-primary text-white"><?= strtoupper(substr($adminName,0,1)) ?></span>
          </div>
          <div class="flex-grow-1 overflow-hidden">
            <div class="text-white small fw-semibold text-truncate"><?= htmlspecialchars($adminName) ?></div>
            <div class="text-white-50 small"><?= htmlspecialchars($adminRole) ?></div>
          </div>
          <a href="/admin/logout.php" class="btn btn-ghost-light btn-sm btn-icon" title="Sign out">
            <i class="ti ti-logout"></i>
          </a>
        </div>
      </div>
    </div>
  </div>
</aside>

<!-- Page wrapper -->
<div class="page-wrapper">
