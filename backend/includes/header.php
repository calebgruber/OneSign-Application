<?php
/**
 * Shared admin header template
 */
$pageTitle = $pageTitle ?? 'Dashboard';
$adminName = $_SESSION['admin_name'] ?? 'Admin';
$adminRole = $_SESSION['admin_role'] ?? 'admin';
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OneSign &mdash; <?= htmlspecialchars($pageTitle) ?></title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
<link rel="stylesheet" href="https://unpkg.com/tabulator-tables@6.2.1/dist/css/tabulator_bootstrap5.min.css">
<link rel="stylesheet" href="/assets/css/onesign.css">
</head>
<body>

<!-- Top Navigation -->
<nav class="navbar navbar-expand-lg onesign-topnav px-3 py-0 shadow-sm">
    <a class="navbar-brand d-flex align-items-center gap-2" href="/admin/index.php">
        <img src="/assets/img/logo.svg" height="32" alt="OneSign">
        <span class="fw-bold text-white fs-5">OneSign</span>
    </a>
    <div class="ms-auto d-flex align-items-center gap-3">
        <span class="text-white-50 small d-none d-md-inline"><i class="bi bi-person-circle me-1"></i><?= htmlspecialchars($adminName) ?></span>
        <span class="badge <?= $adminRole === 'superadmin' ? 'bg-warning text-dark' : 'bg-secondary' ?> small"><?= htmlspecialchars($adminRole) ?></span>
        <a href="/admin/logout.php" class="btn btn-sm btn-outline-light"><i class="bi bi-box-arrow-right"></i></a>
    </div>
</nav>

<div class="d-flex" id="wrapper">
    <!-- Sidebar -->
    <nav id="sidebar" class="onesign-sidebar d-flex flex-column py-3 px-2">
        <ul class="nav flex-column gap-1">
            <li class="nav-item">
                <a class="nav-link onesign-nav-link <?= basename($_SERVER['PHP_SELF']) === 'index.php' ? 'active' : '' ?>" href="/admin/index.php">
                    <i class="bi bi-speedometer2 me-2"></i>Dashboard
                </a>
            </li>
            <li class="nav-item">
                <a class="nav-link onesign-nav-link <?= basename($_SERVER['PHP_SELF']) === 'users.php' ? 'active' : '' ?>" href="/admin/users.php">
                    <i class="bi bi-people me-2"></i>Users
                </a>
            </li>
            <li class="nav-item">
                <a class="nav-link onesign-nav-link <?= basename($_SERVER['PHP_SELF']) === 'cards.php' ? 'active' : '' ?>" href="/admin/cards.php">
                    <i class="bi bi-credit-card-2-front me-2"></i>Cards
                </a>
            </li>
            <li class="nav-item">
                <a class="nav-link onesign-nav-link <?= basename($_SERVER['PHP_SELF']) === 'enroll.php' ? 'active' : '' ?>" href="/admin/enroll.php">
                    <i class="bi bi-person-plus me-2"></i>Enroll
                </a>
            </li>
            <li class="nav-item">
                <a class="nav-link onesign-nav-link <?= basename($_SERVER['PHP_SELF']) === 'audit.php' ? 'active' : '' ?>" href="/admin/audit.php">
                    <i class="bi bi-journal-text me-2"></i>Audit Log
                </a>
            </li>
            <li class="nav-item">
                <a class="nav-link onesign-nav-link <?= basename($_SERVER['PHP_SELF']) === 'workstations.php' ? 'active' : '' ?>" href="/admin/workstations.php">
                    <i class="bi bi-pc-display me-2"></i>Workstations
                </a>
            </li>
            <li class="nav-item mt-3">
                <a class="nav-link onesign-nav-link <?= basename($_SERVER['PHP_SELF']) === 'settings.php' ? 'active' : '' ?>" href="/admin/settings.php">
                    <i class="bi bi-gear me-2"></i>Settings
                </a>
            </li>
        </ul>
    </nav>

    <!-- Main Content -->
    <div id="page-content" class="flex-grow-1 p-4">
