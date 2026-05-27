"""
tray_app.py — System tray icon and balloon/toast notifications for OneSign.

Uses:
  - pystray  (cross-platform tray icon with menu)
  - win10toast (Windows balloon notifications) with ctypes fallback
  - Pillow  (PIL) for tray icon rendering

The tray icon shows:
  - Green/grey status dot on the icon
  - Right-click menu: Status, Enroll card, About, Exit
  - Balloon notification on card tap events
"""

import logging
import os
import subprocess
import sys
import threading
import time

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# ── Icon generation ──────────────────────────────────────────────────────────

_ICON_SIZE = 64
_COLOR_GREEN  = (10, 200, 140, 255)
_COLOR_GREY   = (140, 140, 140, 255)
_COLOR_ORANGE = (247, 103, 7, 255)
_COLOR_BLUE   = (26, 111, 196, 255)
_COLOR_WHITE  = (255, 255, 255, 255)
_COLOR_WHITE_80 = (255, 255, 255, 80)


def _make_icon_image(status: str = "idle") -> Image.Image:
    """
    Draw a simple badge icon with a status dot.
    status: 'idle' | 'connected' | 'locked' | 'auth'
    """
    sz = _ICON_SIZE
    img  = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Badge rectangle
    draw.rounded_rectangle([6, 8, sz - 6, sz - 8], radius=8, fill=_COLOR_BLUE)

    # Magnetic stripe
    draw.rectangle([10, 14, sz - 10, 20], fill=_COLOR_WHITE_80)

    # Person circle
    cx, cy = sz // 2, sz // 2 + 4
    draw.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=_COLOR_WHITE)
    draw.ellipse([cx - 5,  cy - 5,  cx + 5,  cy + 5],  fill=_COLOR_BLUE)

    # Status dot (bottom-right)
    dot_colors = {
        "idle":      _COLOR_GREY,
        "connected": _COLOR_GREEN,
        "locked":    _COLOR_ORANGE,
        "auth":      _COLOR_GREEN,
    }
    dot_color = dot_colors.get(status, _COLOR_GREY)
    d = 14
    draw.ellipse([sz - d - 2, sz - d - 2, sz - 2, sz - 2], fill=dot_color)

    return img


# ── Balloon notifications ────────────────────────────────────────────────────

def _balloon_ctypes(title: str, message: str, duration: int = 5):
    """
    Show a Windows balloon / toast notification using Shell_NotifyIconW.
    Falls back to win10toast if available.
    """
    try:
        from win10toast import ToastNotifier
        _toaster = ToastNotifier()
        _toaster.show_toast(
            title,
            message,
            icon_path=None,
            duration=duration,
            threaded=True,
        )
        return
    except ImportError:
        pass

    # ctypes Shell_NotifyIcon fallback (basic tray balloon)
    try:
        import ctypes
        import ctypes.wintypes as wt

        NIM_MODIFY   = 0x00000001
        NIF_INFO     = 0x00000010
        NIIF_INFO    = 0x00000001

        class NOTIFYICONDATA(ctypes.Structure):
            _fields_ = [
                ("cbSize",           ctypes.c_ulong),
                ("hWnd",             wt.HWND),
                ("uID",              ctypes.c_uint),
                ("uFlags",           ctypes.c_uint),
                ("uCallbackMessage", ctypes.c_uint),
                ("hIcon",            wt.HICON),
                ("szTip",            ctypes.c_wchar * 128),
                ("dwState",          ctypes.c_ulong),
                ("dwStateMask",      ctypes.c_ulong),
                ("szInfo",           ctypes.c_wchar * 256),
                ("uTimeout",         ctypes.c_uint),
                ("szInfoTitle",      ctypes.c_wchar * 64),
                ("dwInfoFlags",      ctypes.c_ulong),
            ]

        nid = NOTIFYICONDATA()
        nid.cbSize     = ctypes.sizeof(NOTIFYICONDATA)
        nid.uFlags     = NIF_INFO
        nid.szInfo     = message[:255]
        nid.szInfoTitle = title[:63]
        nid.uTimeout   = duration * 1000
        nid.dwInfoFlags = NIIF_INFO
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
    except Exception as exc:
        logger.debug("Balloon notification failed: %s", exc)


# ── Tray application ─────────────────────────────────────────────────────────

class TrayApp:
    """
    Manages the system tray icon lifecycle.
    Call start() in a daemon thread; stop() to exit.
    """

    def __init__(self, agent_ref=None):
        self._agent   = agent_ref
        self._icon    = None
        self._status  = "idle"      # idle | connected | locked | auth
        self._status_text = "OneSign Agent — Idle"
        self._lock    = threading.Lock()

    # ── Public API ───────────────────────────────────────────────────────

    def set_status(self, status: str, text: str = None):
        with self._lock:
            self._status = status
            if text:
                self._status_text = text
        if self._icon:
            self._icon.icon  = _make_icon_image(status)
            self._icon.title = self._status_text

    def notify(self, title: str, message: str, duration: int = 5):
        """Show a balloon notification (non-blocking)."""
        t = threading.Thread(
            target=_balloon_ctypes,
            args=(title, message, duration),
            daemon=True,
        )
        t.start()

    def start(self):
        """Build and run the tray icon (blocks until stop() is called)."""
        menu = pystray.Menu(
            pystray.MenuItem(lambda _: self._status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sync with Server", self._on_sync),
            pystray.MenuItem("Show Connection Status", self._on_status),
            pystray.MenuItem("Open Agent Log", self._on_open_log),
            pystray.MenuItem("Open Admin Panel", self._on_open_admin),
            pystray.MenuItem("Enroll Card…",     self._on_enroll),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit Agent",        self._on_exit),
        )
        self._icon = pystray.Icon(
            name="OneSign",
            icon=_make_icon_image("idle"),
            title="OneSign Agent",
            menu=menu,
        )
        self._icon.run()

    def stop(self):
        if self._icon:
            self._icon.stop()

    # ── Menu handlers ────────────────────────────────────────────────────

    def _on_exit(self, icon, item):
        icon.stop()
        if self._agent:
            self._agent.stop()
        os._exit(0)

    def _on_enroll(self, icon, item):
        self.notify(
            "OneSign Enrollment",
            "Start enrollment in the admin panel, then tap the card on this reader.",
            duration=8,
        )
        if self._agent:
            self._agent.start_enrollment_mode()

    def _on_sync(self, icon, item):
        if self._agent:
            self._agent.sync_with_server()

    def _on_status(self, icon, item):
        if self._agent:
            self.notify("OneSign Status", self._agent.get_status_summary(), duration=6)

    def _on_open_log(self, icon, item):
        if not self._agent:
            return
        log_path = self._agent.get_log_file_path()
        if not log_path or not os.path.isfile(log_path):
            self.notify("OneSign Log", "No log file found yet.", duration=5)
            return
        try:
            os.startfile(log_path)  # type: ignore[attr-defined]
        except Exception:
            try:
                subprocess.Popen(["notepad.exe", log_path], close_fds=True)
            except Exception as exc:
                self.notify("OneSign Log Error", f"Could not open log file: {exc}", duration=6)

    def _on_open_admin(self, icon, item):
        import webbrowser
        if self._agent:
            url = self._agent.get_admin_url()
        else:
            url = "http://localhost/admin"
        webbrowser.open(url)
