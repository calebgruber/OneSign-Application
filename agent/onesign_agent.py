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
import socket
import sys
import threading
import time
from pathlib import Path

import requests

# ── Local imports ─────────────────────────────────────────────────────────────
# Allow running from the agent/ directory or from the installed EXE location.
_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

from pcprox    import PcProxReader, PcProxError
from win_login import lock_workstation, unlock_workstation, is_workstation_locked
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
        "dll_path": r"C:\Program Files\RF IDeas\pcProx\pcProxAPI64.dll",
        "poll_interval_ms": "250",
    },
    "behavior": {
        "lock_on_remove":    "true",
        "lock_delay_seconds": "5",
        "reconnect_delay_s":  "10",
        "heartbeat_interval": "30",
    },
}

HOSTNAME = socket.gethostname()


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

        self._running        = False
        self._last_card_hex  = None      # card ID currently on reader
        self._card_absent_since: float | None = None
        self._lock_pending   = False
        self._enrollment_mode = False

        self.tray = TrayApp(agent_ref=self)
        self.reader = PcProxReader(
            dll_path=self.config.get("reader", "dll_path")
        )
        self._session = requests.Session()
        self._session.headers.update({
            "X-Api-Key": self.config.get("server", "api_key"),
            "Content-Type": "application/json",
        })
        self._session.timeout = 8

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self):
        """Start the agent — connects reader, starts threads, runs tray."""
        self._running = True
        logger.info("OneSign Agent starting on %s", HOSTNAME)
        self.tray.notify("OneSign Agent", "Starting up…", duration=3)

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
                self.tray.set_status("connected", f"OneSign — Reader connected on {HOSTNAME}")
                self._poll_loop(poll_ms / 1000.0)
            except PcProxError as exc:
                logger.warning("Reader error: %s — retrying in %ds", exc, reconnect)
                self.tray.set_status("idle", "OneSign — Reader disconnected")
                self.tray.notify("OneSign — Reader Error", str(exc), duration=4)
            finally:
                try:
                    self.reader.disconnect()
                except Exception:
                    pass
            time.sleep(reconnect)

    def _poll_loop(self, interval: float):
        lock_delay = self.config.getfloat("behavior", "lock_delay_seconds", fallback=5.0)
        lock_on_remove = self.config.getboolean("behavior", "lock_on_remove", fallback=True)

        while self._running:
            card_hex = self.reader.get_card_hex()

            # ── Card newly tapped ────────────────────────────────────────────
            if card_hex and card_hex != self._last_card_hex:
                logger.info("Card detected: %s", card_hex)
                self._last_card_hex      = card_hex
                self._card_absent_since  = None
                self._lock_pending       = False

                if self._enrollment_mode:
                    self._handle_enroll(card_hex)
                else:
                    self._handle_auth(card_hex)

            # ── Card still present ───────────────────────────────────────────
            elif card_hex and card_hex == self._last_card_hex:
                self._card_absent_since = None
                self._lock_pending      = False

            # ── Card removed ─────────────────────────────────────────────────
            elif not card_hex and self._last_card_hex:
                if self._card_absent_since is None:
                    self._card_absent_since = time.monotonic()
                    logger.debug("Card removed, starting lock timer (%ss)", lock_delay)

                elapsed = time.monotonic() - self._card_absent_since
                if lock_on_remove and elapsed >= lock_delay and not self._lock_pending:
                    self._lock_pending = True
                    self._last_card_hex = None
                    logger.info("Locking workstation (card removed)")
                    self.tray.notify("OneSign", "Badge removed — locking workstation.", duration=3)
                    self.tray.set_status("locked", "OneSign — Workstation locked")
                    lock_workstation()

            time.sleep(interval)

    # ── Auth / unlock ─────────────────────────────────────────────────────────

    def _handle_auth(self, card_hex: str):
        self.tray.set_status("auth", "OneSign — Authenticating…")
        url = self.config.get("server", "url").rstrip("/") + "/api/auth.php"
        try:
            resp = self._session.post(url, json={
                "card_id":    card_hex,
                "workstation": HOSTNAME,
            })
        except requests.RequestException as exc:
            logger.error("Auth request failed: %s", exc)
            self.tray.notify("OneSign — Error", "Cannot reach server. Check network.", duration=5)
            self.tray.set_status("connected")
            return

        if resp.status_code == 200:
            data = resp.json()
            creds    = data.get("credentials") or {}
            username = creds.get("username", "")
            password = creds.get("password", "")
            domain   = creds.get("domain", ".")
            fullname = data.get("user", {}).get("full_name", username)

            logger.info("Auth success: %s", username)
            self.tray.notify(
                "OneSign — Welcome",
                f"Logging in as {fullname}…",
                duration=4,
            )
            self.tray.set_status("connected", f"OneSign — {fullname}")

            locked = is_workstation_locked()
            ok = unlock_workstation(username, password, domain)
            if not ok:
                self.tray.notify("OneSign — Error", "Login failed. Please use Ctrl+Alt+Del.", duration=6)
        elif resp.status_code == 401:
            logger.warning("Card not enrolled: %s", card_hex)
            self.tray.notify("OneSign — Unknown Badge", "This badge is not enrolled. Contact your administrator.", duration=5)
            self.tray.set_status("connected")
        elif resp.status_code == 403:
            logger.warning("Card disabled: %s", card_hex)
            self.tray.notify("OneSign — Access Denied", "This badge has been disabled.", duration=5)
            self.tray.set_status("connected")
        else:
            logger.error("Auth error %d: %s", resp.status_code, resp.text[:200])
            self.tray.notify("OneSign — Error", f"Server error ({resp.status_code}).", duration=5)
            self.tray.set_status("connected")

    # ── Enrollment mode ───────────────────────────────────────────────────────

    def start_enrollment_mode(self):
        self._enrollment_mode = True
        self._last_card_hex   = None
        logger.info("Enrollment mode activated")

    def _handle_enroll(self, card_hex: str):
        self._enrollment_mode = False
        url = self.config.get("server", "url").rstrip("/") + "/api/enroll.php"
        try:
            resp = self._session.post(url, json={
                "card_id":  card_hex,
                "hostname": HOSTNAME,
                "action":   "submit",
            })
            if resp.status_code == 200:
                logger.info("Card enrolled: %s", card_hex)
                self.tray.notify("OneSign — Enrolled", f"Badge {card_hex} enrolled successfully!", duration=5)
            else:
                err = resp.json().get("error", "Unknown error")
                self.tray.notify("OneSign — Enrollment Failed", err, duration=5)
        except requests.RequestException as exc:
            logger.error("Enroll request failed: %s", exc)
            self.tray.notify("OneSign — Error", "Enrollment failed. Check server connection.", duration=5)

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    def _heartbeat_loop(self):
        interval = self.config.getint("behavior", "heartbeat_interval", fallback=30)
        url = self.config.get("server", "url").rstrip("/") + "/api/heartbeat.php"
        while self._running:
            try:
                locked = is_workstation_locked()
                self._session.post(url, json={
                    "hostname": HOSTNAME,
                    "status":   "locked" if locked else "active",
                })
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
