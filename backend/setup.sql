-- OneSign Application Database Schema
-- Run this script to initialize the database

CREATE DATABASE IF NOT EXISTS onesign CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE onesign;

-- Admin users for the web panel
CREATE TABLE IF NOT EXISTS admin_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(200),
    role ENUM('superadmin', 'admin', 'viewer') NOT NULL DEFAULT 'admin',
    active TINYINT(1) NOT NULL DEFAULT 1,
    last_login DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Windows domain users enrolled in OneSign
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(200),
    department VARCHAR(200),
    windows_domain VARCHAR(100) DEFAULT NULL,
    windows_password_enc TEXT DEFAULT NULL,
    photo_url VARCHAR(500) DEFAULT NULL,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- RFID/proximity cards enrolled to users
CREATE TABLE IF NOT EXISTS cards (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    card_id VARCHAR(64) NOT NULL UNIQUE,
    card_label VARCHAR(200) DEFAULT NULL,
    enrolled_by VARCHAR(100) DEFAULT NULL,
    enrolled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active TINYINT(1) NOT NULL DEFAULT 1,
    last_used DATETIME DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_card_id (card_id),
    INDEX idx_user_id (user_id)
);

-- Workstations/PCs running the OneSign agent
CREATE TABLE IF NOT EXISTS workstations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hostname VARCHAR(200) NOT NULL UNIQUE,
    ip_address VARCHAR(45) DEFAULT NULL,
    os_version VARCHAR(200) DEFAULT NULL,
    agent_version VARCHAR(50) DEFAULT NULL,
    last_heartbeat DATETIME DEFAULT NULL,
    current_user_id INT DEFAULT NULL,
    status ENUM('online', 'offline', 'locked') DEFAULT 'offline',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (current_user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_hostname (hostname)
);

-- Session tracking
CREATE TABLE IF NOT EXISTS sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    workstation_id INT NOT NULL,
    card_id VARCHAR(64) DEFAULT NULL,
    login_method ENUM('card', 'password', 'auto') NOT NULL DEFAULT 'card',
    logged_in_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    logged_out_at DATETIME DEFAULT NULL,
    duration_seconds INT DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (workstation_id) REFERENCES workstations(id),
    INDEX idx_user_id (user_id),
    INDEX idx_workstation_id (workstation_id),
    INDEX idx_logged_in_at (logged_in_at)
);

-- Audit log for all actions
CREATE TABLE IF NOT EXISTS audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    user_id INT DEFAULT NULL,
    card_id VARCHAR(64) DEFAULT NULL,
    workstation VARCHAR(200) DEFAULT NULL,
    ip_address VARCHAR(45) DEFAULT NULL,
    details TEXT DEFAULT NULL,
    success TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_event_type (event_type),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
);

-- Application settings
CREATE TABLE IF NOT EXISTS settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL UNIQUE,
    setting_value TEXT,
    description VARCHAR(500),
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Runtime key/value store with TTL (used for enrollment queue + ping handshakes)
CREATE TABLE IF NOT EXISTS runtime_store (
    store_key VARCHAR(191) NOT NULL PRIMARY KEY,
    store_value TEXT NOT NULL,
    expires_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_expires_at (expires_at)
);

-- API keys for agent authentication
CREATE TABLE IF NOT EXISTS api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    api_key VARCHAR(64) NOT NULL UNIQUE,
    label VARCHAR(200) NOT NULL,
    workstation VARCHAR(200) DEFAULT NULL,
    active TINYINT(1) NOT NULL DEFAULT 1,
    last_used DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_api_key (api_key)
);

-- Default admin user: admin / Admin1234!
INSERT INTO admin_users (username, password_hash, full_name, email, role) VALUES
('admin', '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', 'System Administrator', 'admin@localhost', 'superadmin')
ON DUPLICATE KEY UPDATE username = username;

-- Default settings
INSERT INTO settings (setting_key, setting_value, description) VALUES
('app_name', 'OneSign', 'Application name shown in UI'),
('app_logo', '/assets/img/logo.svg', 'Path to application logo'),
('lock_on_remove', '1', 'Lock workstation when card is removed'),
('lock_delay_seconds', '5', 'Seconds to wait before locking after card removal'),
('session_timeout_minutes', '480', 'Auto-lock after inactivity (minutes)'),
('require_https', '0', 'Require HTTPS for agent connections'),
('encryption_key', '', 'Server-side encryption key (auto-generated)'),
('allow_password_fallback', '1', 'Allow username/password login as fallback'),
('enrollment_mode', 'admin', 'Who can enroll cards: admin or user'),
('credential_provider_enabled', '0', 'Use external credential provider helper for workstation unlocks'),
('credential_provider_command', '', 'Command to invoke credential provider helper (receives JSON on stdin)'),
('credential_provider_timeout_seconds', '20', 'Max seconds to wait for credential provider helper process'),
('lock_background_image', '', 'URL for custom lock overlay background image'),
('lock_logo_image', '', 'URL for custom lock overlay logo image'),
('lock_brand_name', 'Secure log in', 'Brand text shown on lock overlay'),
('lock_color_primary', '#2B4D89', 'Primary lock overlay background color'),
('lock_color_panel', '#1D2A43', 'Right panel lock overlay background color'),
('lock_color_hex', '#F4F6FA', 'Hex tile background color on lock overlay'),
('lock_color_text', '#FFFFFF', 'Primary text color on lock overlay'),
('lock_color_hex_left', '', 'Left hex tile color override'),
('lock_color_hex_top', '', 'Top hex tile color override'),
('lock_color_hex_bottom', '', 'Bottom hex tile color override'),
('lock_color_overlay', 'rgba(0,0,0,0.50)', 'Lockscreen background overlay color'),
('lock_color_submit', '#c9222e', 'Lockscreen submit button color'),
('lock_right_title', 'OneSign', 'Lockscreen right panel title'),
('lock_right_message', 'Welcome back.\\nSingle Sign On is ready when you are.', 'Lockscreen right panel message'),
('emergency_unlock_username', '', 'Emergency unlock username'),
('emergency_unlock_domain', '.', 'Emergency unlock domain'),
('emergency_unlock_password_enc', '', 'Encrypted emergency unlock password')
ON DUPLICATE KEY UPDATE setting_key = setting_key;

-- Generate a default API key
INSERT INTO api_keys (api_key, label) VALUES
(SHA2(CONCAT('onesign-default-', NOW()), 256), 'Default Agent Key')
ON DUPLICATE KEY UPDATE label = label;
