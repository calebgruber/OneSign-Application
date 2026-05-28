"""
onesign_agent.py — Main OneSign Windows Agent

Responsibilities:
  1. Runs as a Windows service (via NSSM) or standalone process.
  2. Connects to the pcProx reader and polls every 250 ms.
  3. On card tap → calls backend /api/auth.php to get Windows credentials.
  4. Unlocks/logs in the workstation with those credentials.
  5. On card removal → locks the workstation after a configurable delay.
  6. Sends a heartbeat every 30 s to /api/heartbeat.php.
  7. Shows balloon notifications and a system tray icon.

Configuration: config.ini (next to the EXE).
"""

import configparser
import logging
import logging.handlers
import os
import platform
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

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
    lock_workstation,
    unlock_workstation,
    unlock_with_credential_provider,
    is_workstation_locked,
)
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
    "credential_provider": {
        "enabled": "false",
        "command": "",
        "timeout_seconds": "20",
    },
}

HOSTNAME = socket.gethostname()
APP_VERSION = "1.0.0"
ENROLLMENT_POLL_INTERVAL_SECONDS = 2.0


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

    def get_server_base_url(self) -> str:
        raw = self.config.get("server", "url", fallback="http://localhost").strip()
        if not raw or "YOUR_SERVER" in raw.upper():
            return "http://localhost"
        return raw.rstrip("/")

    def get_admin_url(self) -> str:
        base = self.get_server_base_url()
        if base.lower().endswith("/admin"):
            return base
        return f"{base}/admin"

    def get_log_file_path(self) -> str | None:
        return str(LOG_FILE) if LOG_FILE else None

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

        # Tray (blocks until exit)
        self.tray.set_status("idle", "OneSign Agent — Ready")
        self.tray.start()

    def stop(self):
        self._running = False
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
                    if (
                        self._active_session_card == card_hex
                        and not is_workstation_locked()
                    ):
                        logger.info("Tap-out detected for %s; locking workstation", card_hex)
                        self.tray.notify("OneSign", "Badge tapped again — locking workstation.", duration=3)
                        self.tray.set_status("locked", "OneSign — Workstation locked")
                        lock_workstation()
                        self._active_session_card = None
                    else:
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
            self.tray.set_status("connected")
            return False

        self._server_connected = (resp.status_code == 200)
        if resp.status_code == 200:
            data = resp.json()
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

            use_credential_provider = self.config.getboolean(
                "credential_provider", "enabled", fallback=False
            )
            if use_credential_provider:
                provider_command = self.config.get(
                    "credential_provider", "command", fallback=""
                )
                provider_timeout = self.config.getint(
                    "credential_provider", "timeout_seconds", fallback=20
                )
                ok = unlock_with_credential_provider(
                    provider_command,
                    username,
                    password,
                    domain,
                    provider_timeout,
                )
                if not ok:
                    logger.warning("Credential provider unlock failed, falling back to secure desktop SendInput flow")
                    ok = unlock_workstation(username, password, domain)
            else:
                ok = unlock_workstation(username, password, domain)

            if not ok:
                self.tray.notify("OneSign — Error", "Login failed. Please use Ctrl+Alt+Del.", duration=6)
                self.tray.set_status("connected")
                return False
            return True
        elif resp.status_code == 401:
            logger.warning("Authentication failed due to API key issue")
            self.tray.notify("OneSign — Unauthorized", "API key rejected. Verify config.ini API key.", duration=6)
            self.tray.set_status("connected")
            return False
        else:
            logger.error("Auth error %d: %s", resp.status_code, resp.text[:200])
            self.tray.notify("OneSign — Error", f"Server error ({resp.status_code}).", duration=5)
            self.tray.set_status("connected")
            return False

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
