# OneSign — Imprivata-Style Tap-and-Go Authentication

An open-source Imprivata OneSign replica for Windows, using an **RF Ideas pcProx** RFID badge reader. Tap your badge to log in or unlock. Remove it to lock. A PHP/Tabler UI admin panel manages users, cards, workstations, audit logs, and settings.

---

## Architecture

```
┌──────────────────────────┐          ┌────────────────────────────────┐
│  Windows Workstation      │  HTTPS   │  PHP Backend (Apache/Nginx)    │
│                           │◄────────►│                                │
│  OneSignAgent.exe         │          │  /api/auth.php  → authenticate │
│  ├── pcprox.py            │          │  /api/heartbeat.php            │
│  │    └── pcProxAPI64.dll │          │  /api/enroll.php               │
│  ├── win_login.py         │          │  /admin/*  → Tabler UI panel   │
│  └── tray_app.py          │          │                                │
│       └── System tray     │          │  MySQL database                │
│           Balloon notices │          └────────────────────────────────┘
└──────────────────────────┘
```

---

## Prerequisites

### Server
- PHP 8.1+ with extensions: `pdo_mysql`, `openssl`
- MySQL 8.0+ (or MariaDB 10.6+)
- Apache 2.4+ (with `mod_rewrite`) or Nginx with PHP-FPM
- HTTPS strongly recommended for production

### Windows Workstation (per machine)
- Windows 10/11 (64-bit)
- RF Ideas pcProx Plus reader (USB HID)
- RF Ideas pcProx DLL (`pcProxAPI64.dll`) — from RF Ideas SDK
- NSSM (Non-Sucking Service Manager) — for running the agent as a service

---

## Installation

### 1. Database Setup

```sql
-- Run as MySQL root:
CREATE DATABASE onesign CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'onesign'@'localhost' IDENTIFIED BY 'STRONG_PASSWORD_HERE';
GRANT ALL PRIVILEGES ON onesign.* TO 'onesign'@'localhost';
FLUSH PRIVILEGES;
```

Then import the schema:
```bash
mysql -u onesign -p onesign < backend/setup.sql
```

### 2. PHP Backend

1. Copy the `backend/` folder to your web server root (e.g. `/var/www/html/onesign/` or `C:\xampp\htdocs\onesign\`).
2. Edit `backend/config/config.php`:
   ```php
   define('DB_HOST', 'localhost');
   define('DB_NAME', 'onesign');
   define('DB_USER', 'onesign');
   define('DB_PASS', 'STRONG_PASSWORD_HERE');
   define('CREDENTIAL_ENC_KEY', 'CHANGE_THIS_TO_A_RANDOM_32_CHAR_KEY');
   ```
3. Enable `mod_rewrite` and allow `.htaccess` overrides in your Apache vhost:
   ```apache
   <Directory /var/www/html/onesign>
       AllowOverride All
   </Directory>
   ```
4. Browse to `http://YOUR_SERVER/onesign/` → redirects to admin login.
   - Default credentials: **admin / password** — **change immediately!**

### 3. Admin Panel First Steps

1. Log in at `/admin/login.php`.
2. Go to **Settings** → change the `Credential Encryption Key`.
3. Go to **Users** → add a Windows user (username = Windows account name, full name, domain, Windows password).
4. Go to **Workstations → API Keys** → create an API key for the workstation.
5. Note the API key — you'll need it when installing the agent.

### 4. Windows Agent

#### Option A — Installer (Recommended)

1. Build or download `OneSignAgentSetup.exe` (see [Building from Source](#building-from-source)).
2. Run as Administrator.
3. When prompted, enter:
   - **Backend Server URL** (e.g. `http://192.168.1.100/onesign`)
   - **API Key** from the admin panel
4. Complete installation — the service starts automatically.
5. The OneSign tray icon appears in the system tray.

#### Option B — Manual Installation

```cmd
:: As Administrator:
copy OneSignAgent.exe  "C:\Program Files\OneSign Agent\"
copy pcProxAPI64.dll   "C:\Program Files\OneSign Agent\"
copy nssm.exe          "C:\Program Files\OneSign Agent\"
copy config.ini        "C:\Program Files\OneSign Agent\"

:: Edit config.ini with server URL and API key, then:
cd "C:\Program Files\OneSign Agent"
install_service.bat
```

---

## Enrolling a Badge

### Method 1 — Admin Panel (Manual Entry)
1. Go to **Enroll Card** in the admin panel.
2. Select the user, enter the card hex ID, and click **Enroll**.

### Method 2 — Live Reader
1. Plug the pcProx reader into a workstation running the agent.
2. In the admin panel, go to **Enroll Card → Live Reader Enrollment**.
3. Select the user and choose the target workstation from the dropdown.
4. Click **Start Live Enrollment** — then tap the badge on the reader.
5. The badge is enrolled automatically.

### Method 3 — Tray Icon
Right-click the OneSign tray icon → **Enroll Card…** → tap the badge.

---

## Tap-and-Go Usage

| Action | Result |
|--------|--------|
| Tap badge on reader (locked screen) | Unlocks workstation and logs in |
| Tap badge (already logged in) | No action (already authenticated) |
| Remove badge | Locks workstation after configured delay |
| Tap unregistered badge | Balloon: "Badge not enrolled" |
| Tap disabled badge | Balloon: "Access denied" |

> **Fallback login:** Press `Ctrl+Alt+Del` → **Switch User** to access the standard Windows login screen.

---

## Configuration Reference

### `agent/config.ini`

| Key | Default | Description |
|-----|---------|-------------|
| `[server] url` | `http://YOUR_SERVER` | Backend URL (no trailing slash) |
| `[server] api_key` | `CHANGE_ME` | API key from admin panel |
| `[reader] dll_path` | `C:\Program Files\OneSign Agent\pcProxAPI64.dll` | Path to pcProx DLL |
| `[reader] poll_interval_ms` | `250` | Card polling interval |
| `[reader] active_device_index` | `-1` | Reader index to use when multiple readers are connected |
| `[behavior] lock_on_remove` | `true` | Lock on badge removal |
| `[behavior] lock_delay_seconds` | `5` | Seconds before locking |
| `[behavior] heartbeat_interval` | `30` | Heartbeat period (seconds) |
| `[credential_provider] enabled` | `false` | Use external credential provider helper for unlocks |
| `[credential_provider] command` | *(empty)* | Command to invoke helper (receives JSON creds on stdin) |
| `[credential_provider] timeout_seconds` | `20` | Helper process timeout in seconds |

Tip: If the reader is not connecting, open the tray menu and use **Reader Control…** to enumerate attached readers, select a device index, reconnect, and run a test read.

### `backend/config/config.php`

| Constant | Description |
|----------|-------------|
| `DB_HOST` | MySQL host |
| `DB_NAME` | Database name |
| `DB_USER` | MySQL user |
| `DB_PASS` | MySQL password |
| `CREDENTIAL_ENC_KEY` | AES-256 key for Windows password encryption |
| `SESSION_LIFETIME` | Admin session lifetime (seconds) |
| `APP_TIMEZONE` | PHP timezone |

---

## Building from Source

### Backend
No build step needed — PHP files are deployed directly.

### Agent EXE

```cmd
cd agent
build.bat
```
Output: `agent\dist\OneSignAgent.exe`
`build.bat` installs dependencies with `python -m pip`/`py -3 -m pip` and builds via `-m PyInstaller`, so `pyinstaller.exe` does not need to be on PATH.

### Installer

1. Install [Inno Setup 6](https://jrsoftware.org/issetup.php).
2. Copy required files to `installer\`:
   - `pcProxAPI64.dll` (from RF Ideas SDK, required on 64-bit installs)
   - `pcProxAPI.dll` (from RF Ideas SDK, required on 32-bit installs)
   - `nssm.exe` (from [nssm.cc](https://nssm.cc))
3. Build the EXE first (see above).
4. Run:
   ```cmd
   iscc installer\setup.iss
   ```
Output: `installer\OneSignAgentSetup.exe`

---

## Security Notes

1. **Always use HTTPS** in production. The backend transmits decrypted Windows passwords over the API.
2. **Change `CREDENTIAL_ENC_KEY`** before enrolling any users.
3. **Change the default admin password** immediately after setup.
4. **Rotate API keys** if a workstation is compromised or decommissioned.
5. Windows passwords are encrypted with **AES-256-GCM** in the database; decrypted only at auth time.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Reader not detected | Check USB connection; verify DLL path in `config.ini`; install RF Ideas drivers |
| "Cannot reach server" | Check network, firewall, server URL in `config.ini` |
| Badge not recognized | Enroll the card first via admin panel |
| Lock screen doesn't unlock | Ensure agent runs as SYSTEM; check `agent.log` at `%PROGRAMDATA%\OneSign\` |
| Admin panel 500 error | Check PHP error log; verify DB credentials in `config.php` |

---

## License

MIT — see LICENSE file.

 
