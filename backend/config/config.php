<?php
/**
 * OneSign Application Configuration
 */

// Application
define('APP_NAME', 'OneSign');
define('APP_VERSION', '1.0.0');
define('BASE_URL', (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on' ? 'https' : 'http') . '://' . ($_SERVER['HTTP_HOST'] ?? 'localhost'));

// Database
define('DB_HOST', 'localhost');
define('DB_PORT', 3306);
define('DB_NAME', 'onesign');
define('DB_USER', 'onesign_user');
define('DB_PASS', 'ChangeMe!SecurePass123');
define('DB_CHARSET', 'utf8mb4');

// Security
define('SESSION_LIFETIME', 3600 * 8); // 8 hours
define('API_RATE_LIMIT', 60);         // requests per minute

// Encryption key for Windows credentials (change this to a random 32-char string!)
define('CREDENTIAL_ENC_KEY', 'CHANGE_THIS_KEY_TO_RANDOM_32CHARS');

// Paths
define('ROOT_PATH', dirname(__DIR__));
define('ASSETS_PATH', ROOT_PATH . '/assets');

// Timezone
date_default_timezone_set('America/Chicago');
