<?php
require_once __DIR__ . '/../includes/auth_check.php';
session_destroy();
header('Location: ' . appBasePath() . '/admin/login.php');
exit;
