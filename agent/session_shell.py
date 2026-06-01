import io
import itertools
import json
import logging
import mimetypes
import os
import queue
import threading
import time
import ctypes
import ctypes.wintypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

import requests

try:
    import webview
except Exception:  # pragma: no cover - depends on host runtime
    webview = None


logger = logging.getLogger(__name__)


class SessionShell:
    """Fullscreen lock overlay controlled by the agent."""

    def __init__(self, on_lock_requested: Callable | None = None, on_password_login: Callable | None = None):
        self._on_lock_requested = on_lock_requested
        self._on_password_login = on_password_login
        self._queue: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self._running = False
        self._ready = threading.Event()
        self._available = webview is not None
        self._theme = {
            "lock_background_image": "",
            "lock_logo_image": "",
            "lock_server_base_url": "",
            "lock_brand_name": "Secure log in",
            "lock_color_primary": "#2B4D89",
            "lock_color_panel": "#1D2A43",
            "lock_color_hex": "#F4F6FA",
            "lock_color_text": "#FFFFFF",
            "lock_color_alert": "#E53935",
            "lock_color_info": "#4A9EFF",
            "lock_color_success": "#4CAF50",
            # Per-hex fill colors for the lock-screen hex cluster.
            # When empty the HTML falls back to lock_color_primary (left hex)
            # or lock_color_panel (top/bottom hexes).
            "lock_color_hex_left": "",
            "lock_color_hex_top": "",
            "lock_color_hex_bottom": "",
            "lock_color_overlay": "rgba(0,0,0,0.50)",
            "lock_color_submit": "#c9222e",
            "lock_right_title": "OneSign",
            "lock_right_message": "Welcome back.\nSingle Sign On is ready when you are.",
        }
        self._status_lock = threading.Lock()
        self._status = {
            "state": "hidden",
            "helper": "Tap your badge or sign in with Windows credentials.",
            "message": "Ready to unlock.",
            "title": "",
            "panel_message": str(self._theme.get("lock_right_message", "Welcome back.\nSingle Sign On is ready when you are.")),
            "workstation": "Unknown",
            "display_name": "",
            "default_username": self._resolve_default_username(),
        }
        self._http_server: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._http_port = 0
        self._webview_window = None
        self._webview_stop = threading.Event()
        self._theme_assets: dict[str, Path] = {}
        self._lockscreen_path = Path(__file__).resolve().with_name("lockscreen.html")
        self._keyboard_guard_stop = threading.Event()
        self._keyboard_guard_thread: threading.Thread | None = None
        self._keyboard_guard_thread_id = 0
        self._keyboard_guard_lock = threading.Lock()

    def _resolve_default_username(self) -> str:
        user = (os.environ.get("USERNAME") or "").strip()
        domain = (os.environ.get("USERDOMAIN") or "").strip()
        if not user or user.upper() == "SYSTEM":
            return ""
        return f"{domain}\\{user}" if domain and domain.upper() != "WORKGROUP" else user

    @property
    def available(self) -> bool:
        return self._available

    def set_theme(self, theme: dict | None):
        payload = dict(theme or {})
        self._theme.update(payload)
        if self._running:
            self._queue.put(("theme", (dict(self._theme),)))

    def show_lock(self, workstation: str):
        if not self._available:
            return
        self._start_if_needed()
        self._queue.put(("show_lock", (workstation,)))

    def show(self, _display_name: str, workstation: str):
        # Backward compatibility with legacy call sites.
        self.show_lock(workstation)

    def hide(self):
        if not self._available or not self._running:
            return
        self._queue.put(("hide", ()))

    def is_visible(self) -> bool:
        state = str(self._get_status().get("state", "hidden"))
        return state != "hidden"

    def stop(self):
        if not self._available or not self._running:
            return
        self._queue.put(("stop", ()))

    def notify_auth_success(self, display_name: str):
        if not self._available or not self._running:
            return
        self._queue.put(("auth_success", (display_name,)))

    def _start_if_needed(self):
        """Wait for the webview UI to be ready (started via run_on_main_thread)."""
        self._ready.wait(timeout=5)

    def _set_status(self, **updates):
        with self._status_lock:
            self._status.update({k: v for k, v in updates.items() if v is not None})

    def _get_status(self) -> dict:
        with self._status_lock:
            return dict(self._status)

    def _lockscreen_asset_path(self) -> Path:
        return self._lockscreen_path

    def _set_keyboard_guard(self, enabled: bool):
        with self._keyboard_guard_lock:
            if enabled:
                if self._keyboard_guard_thread and self._keyboard_guard_thread.is_alive():
                    return
                self._keyboard_guard_stop.clear()
                self._keyboard_guard_thread = threading.Thread(
                    target=self._keyboard_guard_loop,
                    daemon=True,
                    name="OneSign-KeyGuard",
                )
                self._keyboard_guard_thread.start()
                return

            self._keyboard_guard_stop.set()
            thread_id = self._keyboard_guard_thread_id
            if thread_id:
                try:
                    ctypes.windll.user32.PostThreadMessageW(thread_id, 0x0012, 0, 0)  # WM_QUIT
                except Exception:
                    pass

    def _keyboard_guard_loop(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        WH_KEYBOARD_LL = 13
        HC_ACTION = 0
        WM_KEYDOWN = 0x0100
        WM_SYSKEYDOWN = 0x0104
        VK_TAB = 0x09
        VK_ESCAPE = 0x1B
        VK_DELETE = 0x2E
        VK_F4 = 0x73
        VK_LWIN = 0x5B
        VK_RWIN = 0x5C
        VK_MENU = 0x12
        VK_CONTROL = 0x11
        VK_SHIFT = 0x10

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("vkCode", ctypes.wintypes.DWORD),
                ("scanCode", ctypes.wintypes.DWORD),
                ("flags", ctypes.wintypes.DWORD),
                ("time", ctypes.wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.wintypes.HWND),
                ("message", ctypes.wintypes.UINT),
                ("wParam", ctypes.wintypes.WPARAM),
                ("lParam", ctypes.wintypes.LPARAM),
                ("time", ctypes.wintypes.DWORD),
                ("pt", POINT),
                ("lPrivate", ctypes.wintypes.DWORD),
            ]

        def _is_down(vk: int) -> bool:
            try:
                return bool(user32.GetAsyncKeyState(vk) & 0x8000)
            except Exception:
                return False

        proc_type = ctypes.WINFUNCTYPE(ctypes.wintypes.LPARAM, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)

        @proc_type
        def low_level_proc(n_code, w_param, l_param):
            if n_code == HC_ACTION and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = int(info.vkCode)
                alt = _is_down(VK_MENU)
                ctrl = _is_down(VK_CONTROL)
                shift = _is_down(VK_SHIFT)
                should_block = (
                    vk in (VK_LWIN, VK_RWIN)
                    or (vk == VK_TAB and alt)
                    or (vk == VK_F4 and alt)
                    or (vk == VK_ESCAPE and alt)
                    or (vk == VK_ESCAPE and ctrl)
                    or (vk == VK_ESCAPE and ctrl and shift)
                    or (vk == VK_DELETE and ctrl and alt)
                )
                if should_block:
                    return 1
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            low_level_proc,
            kernel32.GetModuleHandleW(None),
            0,
        )
        if not hook:
            logger.warning("Could not install lock keyboard guard")
            return

        self._keyboard_guard_thread_id = int(kernel32.GetCurrentThreadId())
        msg = MSG()
        try:
            while not self._keyboard_guard_stop.is_set():
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result in (0, -1):
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            try:
                user32.UnhookWindowsHookEx(hook)
            except Exception:
                pass
            self._keyboard_guard_thread_id = 0

    def _resolve_local_image(self, source: str) -> Path | None:
        raw = (source or "").strip()
        if not raw:
            return None
        if len(raw) > 1 and raw[1] == ":":
            candidate = Path(raw)
            return candidate if candidate.is_file() else None
        if raw.startswith("\\\\"):
            candidate = Path(raw)
            return candidate if candidate.is_file() else None
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https"}:
            return None
        if parsed.scheme == "file":
            candidate = Path(parsed.path)
            return candidate if candidate.is_file() else None
        source_path = Path(raw)
        if source_path.is_absolute():
            return source_path if source_path.is_file() else None
        base_dir = Path(__file__).resolve().parent
        for candidate in (Path.cwd() / source_path, base_dir / source_path, base_dir.parent / source_path):
            if candidate.is_file():
                return candidate
        return None

    def _resolve_remote_image(self, source: str) -> str | None:
        raw = (source or "").strip()
        if not raw:
            return None
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https"}:
            return raw
        base_url = str(self._theme.get("lock_server_base_url", "")).strip()
        if base_url:
            return urljoin(base_url.rstrip("/") + "/", raw.lstrip("/"))
        return None

    def _build_theme_payload(self) -> dict:
        payload = dict(self._theme)
        assets: dict[str, Path] = {}
        for key in ("lock_background_image", "lock_logo_image"):
            source = str(payload.get(key, "") or "")
            local_path = self._resolve_local_image(source)
            if local_path is not None:
                assets[key] = local_path
                payload[key] = f"/theme-asset/{key}?v={int(local_path.stat().st_mtime_ns)}"
                continue
            payload[key] = self._resolve_remote_image(source) or ""
        self._theme_assets = assets
        return payload

    def _start_http_server(self):
        shell = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # pragma: no cover - noisy
                logger.debug("Lock shell http: " + fmt, *args)

            def _respond_json(self, payload: dict, status: int = 200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _read_body(self) -> bytes:
                length = int(self.headers.get("Content-Length", "0") or 0)
                return self.rfile.read(length) if length > 0 else b""

            def _serve_asset_file(self, file_path: Path):
                if not file_path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                data = file_path.read_bytes()
                content_type, _ = mimetypes.guess_type(str(file_path))
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path
                if path in {"/", "/lockscreen.html"}:
                    file_path = shell._lockscreen_asset_path()
                    if not file_path.is_file():
                        self.send_error(HTTPStatus.NOT_FOUND)
                        return
                    data = file_path.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if path == "/theme":
                    self._respond_json(shell._build_theme_payload())
                    return
                if path == "/status":
                    self._respond_json(shell._get_status())
                    return
                if path.startswith("/theme-asset/"):
                    key = path.rsplit("/", 1)[-1]
                    asset = shell._theme_assets.get(key)
                    if asset is None:
                        self.send_error(HTTPStatus.NOT_FOUND)
                        return
                    self._serve_asset_file(asset)
                    return
                self.send_error(HTTPStatus.NOT_FOUND)

            def do_POST(self):  # noqa: N802
                parsed = urlparse(self.path)
                body = self._read_body()
                payload = {}
                if body:
                    try:
                        payload = json.loads(body.decode("utf-8"))
                    except Exception:
                        payload = {}
                if parsed.path == "/login":
                    username = str(payload.get("username", "")).strip()
                    password = str(payload.get("password", ""))
                    if not username or not password:
                        self._respond_json({"success": False, "message": "Username and password are required."}, status=400)
                        return
                    shell._queue.put(("web_login", (username, password)))
                    self._respond_json({"success": True})
                    return
                if parsed.path == "/lock":
                    shell._queue.put(("lock_requested", ()))
                    self._respond_json({"success": True})
                    return
                self.send_error(HTTPStatus.NOT_FOUND)

        self._http_server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._http_port = int(self._http_server.server_address[1])
        self._http_thread = threading.Thread(target=self._http_server.serve_forever, daemon=True, name="OneSign-LockHttp")
        self._http_thread.start()

    def _stop_http_server(self):
        server = self._http_server
        self._http_server = None
        self._http_port = 0
        if server is None:
            return
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass

    def _push_js(self, script: str):
        window = self._webview_window
        if window is None:
            return
        try:
            window.evaluate_js(script)
        except Exception:
            pass

    def _sync_web_theme(self):
        payload = self._build_theme_payload()
        self._push_js(f"window.oneSignShell?.updateTheme({json.dumps(payload)});")

    def _sync_web_status(self):
        status = self._get_status()
        self._push_js(f"window.oneSignShell?.applyStatus({json.dumps(status)});")

    def _webview_queue_pump(self):
        while not self._webview_stop.is_set():
            try:
                command, args = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if command == "show_lock":
                workstation = str(args[0] or "Unknown")
                self._set_keyboard_guard(True)
                self._set_status(
                    state="locking",
                    helper="Locking workstation...",
                    message="Locking workstation...",
                    title="Locking workstation...",
                    panel_message=str(self._theme.get("lock_right_message", "Welcome back.\nSingle Sign On is ready when you are.")),
                    workstation=workstation,
                    display_name="",
                )
                self._sync_web_theme()
                self._sync_web_status()
                threading.Timer(0.9, lambda: self._queue.put(("lock_ready", (workstation,)))).start()
                window = self._webview_window
                if window is not None:
                    try:
                        window.show()
                        window.set_fullscreen(True)
                    except Exception:
                        pass
            elif command == "hide":
                self._set_keyboard_guard(False)
                self._set_status(state="hidden")
                self._sync_web_status()
                window = self._webview_window
                if window is not None:
                    try:
                        window.hide()
                    except Exception:
                        pass
            elif command == "theme":
                payload = args[0] or {}
                self._theme.update(payload)
                self._sync_web_theme()
            elif command == "lock_ready":
                workstation = str(args[0] or self._get_status().get("workstation") or "Unknown")
                self._set_status(
                    state="ready",
                    helper="Tap your badge or sign in with Windows credentials.",
                    message="Ready to unlock.",
                    title="",
                    panel_message=str(self._theme.get("lock_right_message", "Welcome back.\nSingle Sign On is ready when you are.")),
                    workstation=workstation,
                )
                self._sync_web_status()
            elif command == "auth_failed":
                message = str(args[0] or "Authentication failed.")
                self._set_status(
                    state="failed",
                    helper="Tap your badge or sign in with Windows credentials.",
                    message=message,
                    title="",
                    panel_message=str(self._theme.get("lock_right_message", "Welcome back.\nSingle Sign On is ready when you are.")),
                )
                self._sync_web_status()
            elif command == "auth_success":
                display_name = str(args[0] or "User")
                self._set_status(
                    state="success",
                    helper="Authentication complete.",
                    message="Authenticating user, loading workspace...",
                    title=f"Welcome, {display_name}",
                    panel_message="Authenticating user, loading workspace...",
                    display_name=display_name,
                )
                self._sync_web_status()
                threading.Timer(1.8, lambda: self._queue.put(("hide", ()))).start()
            elif command == "web_login":
                username, password = args
                self._set_status(
                    state="authenticating",
                    helper="Verifying your credentials with OneSign.",
                    message="Authenticating user, loading workspace...",
                    title="Authenticating user, loading workspace...",
                )
                self._sync_web_status()
                if callable(self._on_password_login):
                    threading.Thread(target=self._on_password_login, args=(username, password), daemon=True).start()
            elif command == "lock_requested":
                if callable(self._on_lock_requested):
                    threading.Thread(target=self._on_lock_requested, daemon=True).start()
            elif command == "stop":
                self._set_keyboard_guard(False)
                self._webview_stop.set()
                window = self._webview_window
                if window is not None:
                    try:
                        window.destroy()
                    except Exception:
                        pass

    def _run_webview_ui(self):
        if webview is None:
            raise RuntimeError("pywebview is not installed")
        if not self._lockscreen_asset_path().is_file():
            raise RuntimeError("lockscreen HTML file is missing")

        self._webview_stop.clear()
        self._start_http_server()
        self._set_status(state="hidden")
        self._webview_window = webview.create_window(
            "OneSign Lock",
            url=f"http://127.0.0.1:{self._http_port}/lockscreen.html",
            fullscreen=True,
            frameless=True,
            on_top=True,
            easy_drag=False,
        )
        pump_thread = threading.Thread(target=self._webview_queue_pump, daemon=True, name="OneSign-WebQueue")
        pump_thread.start()
        self._ready.set()
        try:
            webview.start(gui="edgechromium")
        finally:
            self._set_keyboard_guard(False)
            self._webview_stop.set()
            self._webview_window = None
            self._stop_http_server()
            self._running = False
            self._ready.set()

    def start(self):
        """Pre-mark the shell as running so background threads can call show_lock() safely.

        Must be called from the main thread before starting background threads.
        Follow with run_on_main_thread() after all other threads are started.
        """
        self._running = True
        self._ready.clear()

    def run_on_main_thread(self):
        """Block the main thread running the pywebview event loop.

        Call this from the main thread after starting all background threads.
        Returns when the webview is destroyed (i.e. the agent is stopping).
        """
        if not self._available:
            logger.error("pywebview is not installed; HTML lock screen is unavailable.")
            return
        if not self._running:
            self._running = True
            self._ready.clear()
        try:
            self._run_webview_ui()
        except Exception as exc:
            logger.error("HTML lock shell failed: %s", exc)
            self._available = False
            self._running = False
            self._ready.set()

    def notify_auth_failed(self, message: str):
        if not self._available or not self._running:
            return
        self._queue.put(("auth_failed", (message,)))
