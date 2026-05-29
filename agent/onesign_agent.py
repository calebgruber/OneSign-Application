"""
onesign_agent.py — Main OneSign Windows Agent

Responsibilities:
  1. Runs as a Windows service (via NSSM) or standalone process.
  2. Connects to the pcProx reader and polls every 250 ms.
  3. On card tap → calls backend /api/auth.php to get Windows credentials.
  4. Unlocks/logs in the workstation with those credentials.
  5. On card removal / tap-out → locks the workstation.
  6. Sends a heartbeat every 30 s to /api/heartbeat.php.
  7. Shows balloon notifications, a system tray icon, and a fullscreen session shell.

Configuration: config.ini (next to the EXE).
"""

import configparser
import json
import logging
import logging.handlers
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

# ── Local imports ─────────────────────────────────────────────────────────────
# Allow running from the agent/ directory or from the installed EXE location.
if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).resolve().parent
else:
    _BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

from pcprox    import PcProxReader, PcProxError
from win_login import (
    unlock_workstation,
    is_workstation_locked,
)
from session_shell import SessionShell
from tray_app  import TrayApp

# ── Logging setup ─────────────────────────────────────────────────────────────

def _is_elevated() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _build_log_file_handler() -> tuple[logging.Handler | None, Path | None, Exception | None]:
    program_data_dir = Path(os.getenv("PROGRAMDATA", "C:/ProgramData")) / "OneSign"
    local_app_data_dir = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "OneSign"

    # Interactive (non-admin) runs should prefer user-writable logs first.
    if _is_elevated():
        preferred_dirs = [program_data_dir, local_app_data_dir]
    else:
        preferred_dirs = [local_app_data_dir, program_data_dir]

    last_error: Exception | None = None
    for log_dir in preferred_dirs:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "agent.log"
            handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            return handler, log_file, None
        except Exception as exc:
            last_error = exc

    return None, None, last_error


file_handler, LOG_FILE, log_error = _build_log_file_handler()
handlers = [logging.StreamHandler(sys.stdout)]
if file_handler is not None:
    handlers.insert(0, file_handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=handlers,
)
logger = logging.getLogger("onesign")

if LOG_FILE is None and log_error is not None:
    logger.warning("File logging disabled: %s", log_error)

# ── Config defaults ───────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "server": {
        "url":     "http://localhost",
        "api_key": "CHANGE_ME",
    },
    "reader": {
        "dll_path": r"C:\Program Files\OneSign Agent\pcProxAPI64.dll",
        "poll_interval_ms": "250",
        "active_device_index": "-1",
    },
    "behavior": {
        "lock_on_remove":    "true",
        "lock_delay_seconds": "5",
        "reconnect_delay_s":  "10",
        "heartbeat_interval": "30",
    },
    "ui": {
        "fullscreen_shell_enabled": "true",
        "lock_background_image": "",
        "lock_logo_image": "",
        "lock_brand_name": "Secure log in",
        "lock_color_primary": "#2B4D89",
        "lock_color_panel": "#1D2A43",
        "lock_color_hex": "#F4F6FA",
        "lock_color_text": "#FFFFFF",
    },
    "updates": {
        "enabled": "true",
        "github_repo": "calebgruber/OneSign-Application",
        "branch": "main",
        "check_interval_minutes": "30",
        "auto_install": "false",
        "installer_url": "",
        "installer_asset_name": "OneSignAgentSetup.exe",
        "source_update_enabled": "true",
    },
}

HOSTNAME = socket.gethostname()
ENROLLMENT_POLL_INTERVAL_SECONDS = 2.0
GITHUB_API_BASE = "https://api.github.com"


def _load_version_info() -> dict[str, str]:
    info_path = _BASE / "version_info.json"
    if info_path.is_file():
        try:
            payload = json.loads(info_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return {str(k): str(v) for k, v in payload.items()}
        except Exception as exc:
            logger.debug("Could not parse version_info.json: %s", exc)
    return {}


APP_INFO = _load_version_info()
APP_VERSION = APP_INFO.get("version", "1.0.0")
APP_COMMIT = APP_INFO.get("commit", "")


# ─────────────────────────────────────────────────────────────────────────────
class OneSignAgent:
    """Main agent class — owns reader, API client, lock/unlock logic."""

    def __init__(self, config_path: str = None):
        self.config = configparser.ConfigParser()
        # Apply defaults
        for section, values in DEFAULT_CONFIG.items():
            self.config[section] = values

        cfg_file = config_path or str(_BASE / "config.ini")
        if os.path.isfile(cfg_file):
            self.config.read(cfg_file, encoding="utf-8")
        else:
            logger.warning("config.ini not found at %s — using defaults", cfg_file)
        self._config_path = cfg_file

        self._running        = False
        self._last_card_hex  = None      # card ID currently on reader
        self._card_absent_since: float | None = None
        self._lock_pending   = False
        self._enrollment_mode = False
        self._pending_enroll_token: str | None = None
        self._last_enroll_poll_at = 0.0
        self._reader_connected = False
        self._last_reader_error = ""
        self._server_connected = False
        self._last_server_error = ""
        self._reader_lock = threading.Lock()
        self._reader_reconnect_requested = False
        self._active_session_card: str | None = None
        self._tap_rearmed = True

        self.tray = TrayApp(agent_ref=self)
        self.reader = PcProxReader(
            dll_path=self.config.get("reader", "dll_path")
        )
        configured_index = self.config.getint("reader", "active_device_index", fallback=-1)
        if configured_index >= 0:
            self.reader.set_active_device(configured_index)
        self._session = requests.Session()
        self._session.headers.update({
            "X-Api-Key": self.config.get("server", "api_key"),
            "Content-Type": "application/json",
        })
        self._session_timeout = 8
        self._update_lock = threading.Lock()
        self._update_check_pending = False
        self._last_update_check_at = 0.0
        self._last_notified_update_commit: str | None = None
        self._current_commit = self._resolve_local_commit()
        self._current_version = APP_VERSION
        self._ui_settings = dict(self.config.items("ui")) if self.config.has_section("ui") else {}
        self.session_shell = SessionShell(
            on_lock_requested=self._lock_from_session_shell,
            on_password_login=self._handle_password_login,
        )
        self.session_shell.set_theme(self._ui_settings)

    def get_server_base_url(self) -> str:
        raw = self.config.get("server", "url", fallback="http://localhost").strip()
        if not raw or "YOUR_SERVER" in raw.upper():
            return "http://localhost"
        url = raw.rstrip("/")
        # Repair missing colon in scheme separator (e.g. "http//..." → "http://...")
        url = re.sub(r'^(https?)//+', r'\1://', url, flags=re.IGNORECASE)
        # If still no valid scheme, prepend http://
        if not re.match(r'^https?://', url, re.IGNORECASE):
            url = "http://" + url
        if url != raw.rstrip("/"):
            logger.warning(
                "Corrected malformed server URL %r → %r — please fix [server] url in config.ini",
                raw, url,
            )
        return url

    def get_admin_url(self) -> str:
        base = self.get_server_base_url()
        if base.lower().endswith("/admin"):
            return base
        return f"{base}/admin"

    def get_log_file_path(self) -> str | None:
        return str(LOG_FILE) if LOG_FILE else None

    def clear_log(self) -> tuple[bool, str]:
        """Truncate the agent log file."""
        if not LOG_FILE or not LOG_FILE.is_file():
            return False, "No log file found"
        try:
            for handler in logging.root.handlers:
                try:
                    handler.flush()
                except Exception:
                    pass
            LOG_FILE.write_text("", encoding="utf-8")
            logger.info("Log file cleared by user")
            return True, "Log cleared"
        except Exception as exc:
            return False, f"Could not clear log: {exc}"

    def _lock_from_session_shell(self):
        self.session_shell.show_lock(HOSTNAME)
        self._active_session_card = None
        self.tray.set_status("locked", "OneSign — Workstation locked by agent")

    def _apply_server_settings(self, payload: dict[str, Any] | None):
        if not isinstance(payload, dict):
            return
        settings = payload.get("settings")
        if not isinstance(settings, dict):
            return
        ui = settings.get("ui")
        if isinstance(ui, dict):
            normalized = {}
            for key, val in ui.items():
                if val is None:
                    continue
                normalized[str(key)] = str(val)
            if normalized:
                self._ui_settings.update(normalized)
                self.session_shell.set_theme(self._ui_settings)

    def get_status_summary(self) -> str:
        reader_state = "Connected" if self._reader_connected else "Disconnected"
        server_state = "Connected" if self._server_connected else "Disconnected"
        return f"Reader: {reader_state} | Server: {server_state}"

    def get_reader_control_status(self) -> dict[str, Any]:
        selected = self.reader.get_active_device_index()
        return {
            "connected": self._reader_connected,
            "selected_index": selected,
            "dll_path": self.config.get("reader", "dll_path"),
            "last_error": self._last_reader_error,
        }

    def enumerate_readers(self) -> tuple[list[dict], str | None]:
        temp_reader = PcProxReader(dll_path=self.config.get("reader", "dll_path"))
        selected = self.reader.get_active_device_index()
        if selected >= 0:
            temp_reader.set_active_device(selected)
        try:
            return temp_reader.list_devices(), None
        except Exception as exc:
            return [], str(exc)

    def select_reader_index(self, index: int) -> tuple[bool, str]:
        if index < 0:
            return False, "Invalid reader index"
        self.reader.set_active_device(index)
        self.config.set("reader", "active_device_index", str(index))
        with self._reader_lock:
            self._reader_reconnect_requested = True
        return True, f"Reader {index} selected; reconnecting"

    def reconnect_reader(self) -> tuple[bool, str]:
        with self._reader_lock:
            self._reader_reconnect_requested = True
        return True, "Reader reconnect requested"

    def read_card_once(self, timeout_seconds: float = 5.0) -> str | None:
        deadline = time.monotonic() + max(0.5, float(timeout_seconds))
        while time.monotonic() < deadline:
            card = self.reader.get_card_hex()
            if card:
                return card
            time.sleep(0.15)
        return None

    def sync_with_server(self) -> tuple[bool, str]:
        ok, msg = self._send_heartbeat_once()
        if ok:
            self.tray.notify("OneSign — Sync", "Server sync completed successfully.", duration=4)
            return True, msg
        self.tray.notify("OneSign — Sync Failed", msg, duration=6)
        return False, msg

    def check_for_updates(self, manual: bool = False, install: bool = False) -> tuple[bool, str]:
        if not self.config.getboolean("updates", "enabled", fallback=True):
            msg = "Updates are disabled in config.ini."
            if manual:
                self.tray.notify("OneSign Updates", msg, duration=5)
            return False, msg

        if not self._update_lock.acquire(blocking=False):
            msg = "Update check already in progress."
            if manual:
                self.tray.notify("OneSign Updates", msg, duration=4)
            return False, msg

        try:
            repo = self.config.get("updates", "github_repo", fallback="calebgruber/OneSign-Application").strip()
            branch = self.config.get("updates", "branch", fallback="main").strip()
            latest_commit, err = self._fetch_latest_commit(repo, branch)
            if err or not latest_commit:
                msg = err or "Could not check for updates."
                if manual:
                    self.tray.notify("OneSign Update Check Failed", msg, duration=6)
                return False, msg

            current = self._current_commit
            if current and latest_commit.lower() == current.lower():
                msg = f"Already up to date ({latest_commit[:7]})."
                if manual:
                    self.tray.notify("OneSign Updates", msg, duration=4)
                return True, msg

            update_msg = (
                f"Update available: {latest_commit[:7]}"
                + (f" (current {current[:7]})" if current else "")
            )
            if not install:
                if manual or self._last_notified_update_commit != latest_commit:
                    self.tray.notify("OneSign Update Available", update_msg, duration=6)
                    self._last_notified_update_commit = latest_commit
                return True, update_msg

            if self._can_run_source_update():
                self.tray.notify("OneSign Updater", "Pulling latest source and rebuilding…", duration=5)
                ok, launch_msg = self._launch_source_update(branch)
            else:
                self.tray.notify("OneSign Updater", "Downloading update package…", duration=4)
                installer_path, download_err = self._download_update_installer(repo)
                if download_err or not installer_path:
                    msg = download_err or "Update download failed."
                    self.tray.notify("OneSign Update Failed", msg, duration=6)
                    return False, msg
                ok, launch_msg = self._launch_update_installer(installer_path)
            if not ok:
                self.tray.notify("OneSign Update Failed", launch_msg, duration=7)
                return False, launch_msg

            self.tray.notify("OneSign Updating", "Installer started. The agent will restart automatically.", duration=6)
            logger.info("Update launched from %s", installer_path)
            self.stop()
            os._exit(0)
        finally:
            self._update_lock.release()

    def _resolve_local_commit(self) -> str:
        if APP_COMMIT:
            return APP_COMMIT
        if getattr(sys, "frozen", False):
            return ""
        try:
            raw = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(_BASE.parent),
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            return raw
        except Exception:
            return ""

    def _safe_temp_subdir(self, *parts: str) -> Path | None:
        try:
            temp_root = Path(tempfile.gettempdir()).resolve()
            candidate = temp_root.joinpath(*parts).resolve()
            if candidate == temp_root or temp_root in candidate.parents:
                candidate.mkdir(parents=True, exist_ok=True)
                return candidate
        except Exception:
            return None
        return None

    def _can_run_source_update(self) -> bool:
        if not self.config.getboolean("updates", "source_update_enabled", fallback=True):
            return False
        repo_root = _BASE.parent
        build_script = repo_root / "agent" / "build.bat"
        git_dir = repo_root / ".git"
        if not build_script.is_file() or not git_dir.exists():
            return False
        try:
            subprocess.check_output(["git", "--version"], stderr=subprocess.DEVNULL, text=True)
            return True
        except Exception:
            return False

    def _launch_source_update(self, branch: str) -> tuple[bool, str]:
        branch = (branch or "main").strip()
        if not re.match(r"^[A-Za-z0-9._/-]+$", branch):
            return False, "Invalid update branch name"

        repo_root = _BASE.parent
        agent_dir = repo_root / "agent"
        build_script = agent_dir / "build.bat"
        if not build_script.is_file():
            return False, "Source update build script not found"

        if getattr(sys, "frozen", False):
            restart_cmd = f'start "" "{sys.executable}" "{self._config_path}"'
        else:
            restart_cmd = (
                f'start "" "{sys.executable}" '
                f'"{agent_dir / "onesign_agent.py"}" "{self._config_path}"'
            )

        update_dir = self._safe_temp_subdir("OneSign", "updates")
        if update_dir is None:
            return False, "Could not prepare update directory"
        script_path = update_dir / "run_onesign_source_update.cmd"

        lines = [
            "@echo off",
            "setlocal",
            f'cd /d "{repo_root}"',
            f'git fetch origin "{branch}"',
            "if errorlevel 1 goto :fail",
            f'git checkout "{branch}"',
            "if errorlevel 1 goto :fail",
            f'git reset --hard "origin/{branch}"',
            "if errorlevel 1 goto :fail",
            f'cd /d "{agent_dir}"',
            f'call "{build_script}"',
            "if errorlevel 1 goto :fail",
        ]
        if getattr(sys, "frozen", False):
            lines.extend([
                'if exist "dist\\OneSignAgent.exe" (',
                '  taskkill /f /im OneSignAgent.exe >nul 2>&1',
                "  timeout /t 2 /nobreak >nul",
                f'  copy /y "dist\\OneSignAgent.exe" "{Path(sys.executable)}" >nul 2>&1',
                ")",
            ])
        lines.extend([
            "net stop OneSignAgent >nul 2>&1",
            "net start OneSignAgent >nul 2>&1",
            restart_cmd,
            "goto :cleanup",
            ":fail",
            "exit /b 1",
            ":cleanup",
            'del /q "%~f0" >nul 2>&1',
            "",
        ])
        try:
            script_path.write_text("\r\n".join(lines), encoding="utf-8")
            creation_flags = 0
            if hasattr(subprocess, "DETACHED_PROCESS"):
                creation_flags |= subprocess.DETACHED_PROCESS
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                ["cmd.exe", "/C", str(script_path)],
                close_fds=True,
                creationflags=creation_flags,
            )
            return True, "Source update launched"
        except Exception as exc:
            return False, f"Could not launch source update: {exc}"

    def _fetch_latest_commit(self, repo: str, branch: str) -> tuple[str | None, str | None]:
        url = f"{GITHUB_API_BASE}/repos/{repo}/commits/{branch}"
        try:
            resp = requests.get(
                url,
                timeout=15,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "OneSign-Agent-Updater",
                },
            )
        except requests.RequestException as exc:
            return None, f"Could not reach GitHub: {exc}"

        if resp.status_code != 200:
            return None, f"GitHub update check returned HTTP {resp.status_code}"
        try:
            payload = resp.json()
        except Exception:
            return None, "GitHub update response was not valid JSON"
        sha = str(payload.get("sha", "")).strip()
        if not sha:
            return None, "GitHub update response did not include a commit SHA"
        return sha, None

    def _resolve_installer_url(self, repo: str) -> tuple[str, str]:
        custom_url = self.config.get("updates", "installer_url", fallback="").strip()
        if custom_url:
            return custom_url, "custom"
        asset_name = self.config.get("updates", "installer_asset_name", fallback="OneSignAgentSetup.exe").strip()
        if not asset_name:
            asset_name = "OneSignAgentSetup.exe"
        return f"https://github.com/{repo}/releases/latest/download/{asset_name}", "release"

    def _download_update_installer(self, repo: str) -> tuple[str | None, str | None]:
        installer_url, _ = self._resolve_installer_url(repo)
        parsed = urlparse(installer_url)
        if parsed.scheme.lower() != "https":
            return None, "Installer URL must use HTTPS"

        update_dir = self._safe_temp_subdir("OneSign", "updates")
        if update_dir is None:
            return None, "Could not prepare update directory"
        dest_path = update_dir / "OneSignAgentSetup-latest.exe"

        try:
            with requests.get(
                installer_url,
                stream=True,
                timeout=60,
                headers={"User-Agent": "OneSign-Agent-Updater"},
            ) as resp:
                if resp.status_code != 200:
                    return None, f"Installer download returned HTTP {resp.status_code}"
                with open(dest_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            fh.write(chunk)
        except requests.RequestException as exc:
            return None, f"Download failed: {exc}"
        except Exception as exc:
            return None, f"Could not write installer: {exc}"

        try:
            size = dest_path.stat().st_size
        except Exception:
            size = 0
        if size < 1024:
            return None, "Downloaded installer is invalid or empty"
        return str(dest_path), None

    def _launch_update_installer(self, installer_path: str) -> tuple[bool, str]:
        if not os.path.isfile(installer_path):
            return False, "Downloaded installer was not found"

        update_dir = self._safe_temp_subdir("OneSign", "updates")
        if update_dir is None:
            return False, "Could not prepare update directory"
        script_path = update_dir / "run_onesign_update.cmd"
        install_cmd = f'"{installer_path}"'
        if _is_elevated():
            install_cmd = (
                f'"{installer_path}" /VERYSILENT /SUPPRESSMSGBOXES '
                f'/NORESTART /SP- /TASKS="installservice"'
            )
        script_content = "\r\n".join([
            "@echo off",
            "timeout /t 2 /nobreak >nul",
            install_cmd,
            "set RC=%ERRORLEVEL%",
            "if \"%RC%\"==\"0\" (",
            "  net stop OneSignAgent >nul 2>&1",
            "  net start OneSignAgent >nul 2>&1",
            ")",
            f'del /q "{installer_path}" >nul 2>&1',
            "del /q \"%~f0\" >nul 2>&1",
            "",
        ])
        try:
            script_path.write_text(script_content, encoding="utf-8")
            creation_flags = 0
            if hasattr(subprocess, "DETACHED_PROCESS"):
                creation_flags |= subprocess.DETACHED_PROCESS
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                ["cmd.exe", "/C", str(script_path)],
                close_fds=True,
                creationflags=creation_flags,
            )
            return True, "Installer launched"
        except Exception as exc:
            return False, f"Could not launch installer: {exc}"

    def _send_heartbeat_once(self) -> tuple[bool, str]:
        url = self.get_server_base_url() + "/api/heartbeat.php"
        payload = {
            "workstation": HOSTNAME,
            "status": "locked" if is_workstation_locked() else "online",
            "os_version": platform.platform(),
            "agent_version": APP_VERSION,
        }
        try:
            resp = self._session.post(url, json=payload, timeout=self._session_timeout)
        except requests.RequestException as exc:
            self._server_connected = False
            self._last_server_error = str(exc)
            return False, f"Cannot reach server: {exc}"

        if resp.status_code != 200:
            self._server_connected = False
            self._last_server_error = f"HTTP {resp.status_code}"
            return False, f"Server returned HTTP {resp.status_code}"

        try:
            data = resp.json()
        except Exception:
            data = {}
        self._apply_server_settings(data if isinstance(data, dict) else {})
        self._server_connected = True
        self._last_server_error = ""
        return True, "Heartbeat OK"

    def _get_enrollment_token(self) -> str | None:
        url = self.get_server_base_url() + "/api/enroll.php"
        try:
            resp = self._session.get(
                url,
                params={"workstation": HOSTNAME},
                timeout=self._session_timeout,
            )
            if resp.status_code != 200:
                logger.debug("Enrollment poll failed HTTP %d", resp.status_code)
                return None
            payload = resp.json()
            if payload.get("pending") and payload.get("token"):
                return str(payload.get("token"))
            return None
        except Exception as exc:
            logger.debug("Enrollment poll error: %s", exc)
            return None

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self):
        """Start the agent — connects reader, starts threads, runs tray."""
        self._running = True
        logger.info("OneSign Agent starting on %s", HOSTNAME)
        self.tray.notify("OneSign Agent", "Starting up…", duration=3)
        self.sync_with_server()

        # Heartbeat thread
        t_hb = threading.Thread(target=self._heartbeat_loop, daemon=True)
        t_hb.start()

        # Reader polling thread
        t_rd = threading.Thread(target=self._reader_loop, daemon=True)
        t_rd.start()

        # Auto-update thread
        t_upd = threading.Thread(target=self._update_loop, daemon=True)
        t_upd.start()

        # Tray (blocks until exit)
        self.tray.set_status("idle", "OneSign Agent — Ready")
        self.tray.start()

    def stop(self):
        self._running = False
        self.session_shell.stop()
        try:
            self.reader.disconnect()
        except Exception:
            pass
        logger.info("OneSign Agent stopped")

    # ── Reader loop ───────────────────────────────────────────────────────────

    def _reader_loop(self):
        poll_ms    = self.config.getint("reader", "poll_interval_ms", fallback=250)
        reconnect  = self.config.getint("behavior", "reconnect_delay_s", fallback=10)

        while self._running:
            try:
                self.reader.connect()
                self._reader_connected = True
                self._last_reader_error = ""
                self.tray.set_status("connected", f"OneSign — Reader connected on {HOSTNAME}")
                self._poll_loop(poll_ms / 1000.0)
            except PcProxError as exc:
                self._reader_connected = False
                self._last_reader_error = str(exc)
                logger.warning("Reader error: %s — retrying in %ds", exc, reconnect)
                self.tray.set_status("idle", "OneSign — Reader disconnected")
                self.tray.notify("OneSign — Reader Error", str(exc), duration=4)
            finally:
                try:
                    self.reader.disconnect()
                except Exception:
                    pass
                self._reader_connected = False
            sleep_for = reconnect
            with self._reader_lock:
                if self._reader_reconnect_requested:
                    self._reader_reconnect_requested = False
                    sleep_for = 0
            time.sleep(sleep_for)

    def _poll_loop(self, interval: float):
        while self._running:
            card_hex = self.reader.get_card_hex()
            now = time.monotonic()
            self._refresh_enrollment_mode(now)

            # ── Card tap detected ─────────────────────────────────────────────
            if card_hex:
                if card_hex == self._last_card_hex and not self._tap_rearmed:
                    with self._reader_lock:
                        if self._reader_reconnect_requested:
                            self._reader_reconnect_requested = False
                            break
                    time.sleep(interval)
                    continue
                logger.info("Card detected: %s", card_hex)
                self._last_card_hex      = card_hex
                self._card_absent_since  = None
                self._lock_pending       = False
                self._tap_rearmed = False

                if self._enrollment_mode:
                    self._handle_enroll(card_hex, self._pending_enroll_token)
                else:
                    locked = is_workstation_locked()
                    if not locked:
                        if self._active_session_card and card_hex == self._active_session_card:
                            logger.info("Tap-out: activating agent lock overlay for card %s", card_hex)
                            self.tray.notify("OneSign", "Badge tapped — locking screen.", duration=3)
                            self.tray.set_status("locked", "OneSign — Screen locked")
                            self.session_shell.show_lock(HOSTNAME)
                            self._active_session_card = None
                        else:
                            logger.info("Tap switch-user: authenticating card %s", card_hex)
                            self.session_shell.show_lock(HOSTNAME)
                            auth_ok = self._handle_auth(card_hex)
                            if auth_ok:
                                self._active_session_card = card_hex
                            else:
                                self._active_session_card = None
                    else:
                        # Workstation is locked — authenticate and unlock
                        auth_ok = self._handle_auth(card_hex)
                        if auth_ok:
                            self._active_session_card = card_hex
                        else:
                            self._active_session_card = None
            else:
                self._tap_rearmed = True

            with self._reader_lock:
                if self._reader_reconnect_requested:
                    self._reader_reconnect_requested = False
                    break

            time.sleep(interval)

    def _refresh_enrollment_mode(self, now: float | None = None):
        now = now if now is not None else time.monotonic()
        if (now - self._last_enroll_poll_at) < ENROLLMENT_POLL_INTERVAL_SECONDS:
            return
        self._last_enroll_poll_at = now
        pending_token = self._get_enrollment_token()
        if pending_token:
            first_detect = pending_token != self._pending_enroll_token
            self._pending_enroll_token = pending_token
            if not self._enrollment_mode:
                # Just entered enrollment mode — clear tracked card state so the
                # very next badge tap is processed as an enroll event even if the
                # same card was already on the reader before enrollment started.
                self._last_card_hex = None
                self._tap_rearmed = True
            self._enrollment_mode = True
            if first_detect:
                logger.info("Enrollment request received for workstation %s", HOSTNAME)
                self.tray.notify("OneSign Enrollment", "Enrollment mode active. Tap a badge to enroll.", duration=6)
            return
        self._pending_enroll_token = None
        self._enrollment_mode = False

    # ── Auth / unlock ─────────────────────────────────────────────────────────

    def _handle_auth(self, card_hex: str) -> bool:
        self.tray.set_status("auth", "OneSign — Authenticating…")
        url = self.get_server_base_url() + "/api/auth.php"
        try:
            resp = self._session.post(url, json={
                "card_id":    card_hex,
                "workstation": HOSTNAME,
            }, timeout=self._session_timeout)
        except requests.RequestException as exc:
            logger.error("Auth request failed: %s", exc)
            self._server_connected = False
            self._last_server_error = str(exc)
            self.tray.notify("OneSign — Error", "Cannot reach server. Check network.", duration=5)
            self.session_shell.notify_auth_failed("Cannot reach server.")
            self.tray.set_status("connected")
            return False

        self._server_connected = (resp.status_code == 200)
        if resp.status_code == 200:
            data = resp.json()
            self._apply_server_settings(data if isinstance(data, dict) else {})
            if not data.get("authenticated"):
                reason = data.get("reason", "unknown")
                if reason == "card_not_found":
                    self.tray.notify("OneSign — Unknown Badge", "This badge is not enrolled. Contact your administrator.", duration=5)
                elif reason == "card_disabled":
                    self.tray.notify("OneSign — Access Denied", "This badge has been disabled.", duration=5)
                elif reason == "user_disabled":
                    self.tray.notify("OneSign — Access Denied", "User account is disabled.", duration=5)
                else:
                    self.tray.notify("OneSign — Access Denied", f"Authentication failed ({reason}).", duration=5)
                self.session_shell.notify_auth_failed("Badge not recognized.")
                self.tray.set_status("connected")
                return False

            creds    = data.get("credentials") or {}
            username = creds.get("username", "")
            password = creds.get("password", "")
            domain   = creds.get("domain", ".")
            fullname = data.get("user", {}).get("full_name", username)

            if not username or not password:
                self.tray.notify("OneSign — Missing Credentials", "User has no Windows credentials configured in admin panel.", duration=6)
                self.tray.set_status("connected")
                return False

            logger.info("Auth success: %s", username)
            self.tray.notify(
                "OneSign — Welcome",
                f"Logging in as {fullname}…",
                duration=4,
            )
            self.tray.set_status("connected", f"OneSign — {fullname}")

            ok = True
            if is_workstation_locked():
                ok = unlock_workstation(username, password, domain)

            if not ok:
                self.tray.notify("OneSign — Error", "Login failed. Please use Ctrl+Alt+Del.", duration=6)
                self.session_shell.notify_auth_failed("Authentication failed.")
                self.tray.set_status("connected")
                return False
            self.session_shell.hide()
            return True
        elif resp.status_code == 401:
            logger.warning("Authentication failed due to API key issue")
            self.tray.notify("OneSign — Unauthorized", "API key rejected. Verify config.ini API key.", duration=6)
            self.session_shell.notify_auth_failed("Agent API key rejected.")
            self.tray.set_status("connected")
            return False
        else:
            logger.error("Auth error %d: %s", resp.status_code, resp.text[:200])
            self.tray.notify("OneSign — Error", f"Server error ({resp.status_code}).", duration=5)
            self.session_shell.notify_auth_failed("Server error during auth.")
            self.tray.set_status("connected")
            return False

    def _handle_password_login(self, username: str, password: str):
        username = (username or "").strip()
        if not username or not password:
            self.session_shell.notify_auth_failed("Username and password are required.")
            return

        url = self.get_server_base_url() + "/api/password_auth.php"
        try:
            resp = self._session.post(url, json={
                "username": username,
                "password": password,
                "workstation": HOSTNAME,
            }, timeout=self._session_timeout)
        except requests.RequestException as exc:
            self._server_connected = False
            self._last_server_error = str(exc)
            self.session_shell.notify_auth_failed("Cannot reach server.")
            return

        if resp.status_code != 200:
            msg = "Authentication failed."
            try:
                payload = resp.json()
                reason = str(payload.get("reason", "")).strip()
                if reason == "password_fallback_disabled":
                    msg = "Password login is disabled by admin."
            except Exception:
                pass
            self.session_shell.notify_auth_failed(msg)
            return

        try:
            data = resp.json()
        except Exception:
            self.session_shell.notify_auth_failed("Invalid server response.")
            return

        self._apply_server_settings(data if isinstance(data, dict) else {})
        if not data.get("authenticated"):
            self.session_shell.notify_auth_failed("Invalid username or password.")
            return

        creds = data.get("credentials") or {}
        cred_username = creds.get("username", "")
        cred_password = creds.get("password", "")
        domain = creds.get("domain", ".")
        full_name = (data.get("user") or {}).get("full_name", username)

        unlock_ok = True
        if is_workstation_locked():
            unlock_ok = bool(cred_username and cred_password and unlock_workstation(cred_username, cred_password, domain))
        if not unlock_ok:
            self.session_shell.notify_auth_failed("Windows login failed.")
            return

        self._active_session_card = None
        self.tray.notify("OneSign — Welcome", f"Logging in as {full_name}…", duration=4)
        self.tray.set_status("connected", f"OneSign — {full_name}")
        self.session_shell.hide()

    # ── Enrollment mode ───────────────────────────────────────────────────────

    def start_enrollment_mode(self):
        self._enrollment_mode = True
        self._last_card_hex   = None
        self._active_session_card = None
        logger.info("Enrollment mode activated")

    def _handle_enroll(self, card_hex: str, token: str | None = None):
        enroll_token = token or self._pending_enroll_token or self._get_enrollment_token()
        if not enroll_token:
            self._enrollment_mode = False
            self._pending_enroll_token = None
            self.tray.notify(
                "OneSign — Enrollment Pending",
                "No enrollment request found. Start enrollment from the admin panel first.",
                duration=6,
            )
            return

        url = self.get_server_base_url() + "/api/enroll.php"
        try:
            resp = self._session.put(url, json={
                "token": enroll_token,
                "card_id": card_hex,
            }, timeout=self._session_timeout)
            if resp.status_code in (200, 201):
                logger.info("Card enrolled: %s", card_hex)
                self.tray.notify("OneSign — Enrolled", f"Badge {card_hex} enrolled successfully!", duration=5)
                self._pending_enroll_token = None
                self._enrollment_mode = False
                self._last_card_hex = None
            else:
                err = "Unknown error"
                try:
                    err = (resp.json() or {}).get("error", "Unknown error")
                except Exception:
                    pass
                if resp.status_code in (400, 404, 409):
                    self._pending_enroll_token = None
                    self._enrollment_mode = False
                self.tray.notify("OneSign — Enrollment Failed", err, duration=5)
        except requests.RequestException as exc:
            logger.error("Enroll request failed: %s", exc)
            self.tray.notify("OneSign — Error", "Enrollment failed. Check server connection.", duration=5)

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    def _heartbeat_loop(self):
        interval = self.config.getint("behavior", "heartbeat_interval", fallback=30)
        while self._running:
            try:
                ok, msg = self._send_heartbeat_once()
                if not ok:
                    logger.debug("Heartbeat failed: %s", msg)
            except Exception as exc:
                logger.debug("Heartbeat failed: %s", exc)
            time.sleep(interval)

    def _update_loop(self):
        interval_minutes = max(
            1,
            self.config.getint("updates", "check_interval_minutes", fallback=30),
        )
        sleep_seconds = 5
        while self._running:
            now = time.monotonic()
            should_check = (
                self.config.getboolean("updates", "enabled", fallback=True)
                and (
                    self._last_update_check_at <= 0
                    or (now - self._last_update_check_at) >= (interval_minutes * 60)
                )
            )
            if should_check and not self._update_check_pending:
                self._update_check_pending = True
                try:
                    auto_install = self.config.getboolean("updates", "auto_install", fallback=False)
                    self.check_for_updates(manual=False, install=auto_install)
                finally:
                    self._last_update_check_at = time.monotonic()
                    self._update_check_pending = False
            time.sleep(sleep_seconds)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    cfg_path = None
    if len(sys.argv) > 1:
        cfg_path = sys.argv[1]
    agent = OneSignAgent(config_path=cfg_path)
    try:
        agent.run()
    except KeyboardInterrupt:
        agent.stop()


if __name__ == "__main__":
    main()
