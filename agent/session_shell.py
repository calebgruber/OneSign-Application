import io
import itertools
import json
import logging
import mimetypes
import queue
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

import requests

try:
    import tkinter as tk
except Exception:  # pragma: no cover - depends on host runtime
    tk = None

try:
    from PIL import Image, ImageOps, ImageTk
except Exception:  # pragma: no cover - depends on host runtime
    Image = None
    ImageOps = None
    ImageTk = None

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
        self._thread: threading.Thread | None = None
        self._running = False
        self._ready = threading.Event()
        self._available = (webview is not None) or (tk is not None)
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
        }
        self._http_server: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._http_port = 0
        self._webview_window = None
        self._webview_stop = threading.Event()
        self._theme_assets: dict[str, Path] = {}
        self._lockscreen_path = Path(__file__).resolve().with_name("lockscreen.html")

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

    def stop(self):
        if not self._available or not self._running:
            return
        self._queue.put(("stop", ()))

    def notify_auth_success(self, display_name: str):
        if not self._available or not self._running:
            return
        self._queue.put(("auth_success", (display_name,)))

    def _start_if_needed(self):
        if self._running:
            return
        self._running = True
        self._ready.clear()
        self._thread = threading.Thread(target=self._run_ui, daemon=True, name="OneSign-SessionShell")
        self._thread.start()
        self._ready.wait(timeout=5)

    def _set_status(self, **updates):
        with self._status_lock:
            self._status.update({k: v for k, v in updates.items() if v is not None})

    def _get_status(self) -> dict:
        with self._status_lock:
            return dict(self._status)

    def _lockscreen_asset_path(self) -> Path:
        if self._lockscreen_path.is_file():
            return self._lockscreen_path
        base_dir = Path(__file__).resolve().parent
        for name in ("imprivata-login.html", "imprivata-login (1).html"):
            candidate = base_dir / name
            if candidate.is_file():
                return candidate
        return base_dir / "lockscreen.html"

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
                if path == "/hexagon.svg":
                    self._serve_asset_file(shell._lockscreen_asset_path().parent / "hexagon.svg")
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
        )
        pump_thread = threading.Thread(target=self._webview_queue_pump, daemon=True, name="OneSign-WebQueue")
        pump_thread.start()
        self._ready.set()
        try:
            webview.start(gui="edgechromium")
        finally:
            self._webview_stop.set()
            self._webview_window = None
            self._stop_http_server()
            self._running = False
            self._ready.set()

    def _run_ui(self):
        if webview is not None and threading.current_thread() is threading.main_thread():
            try:
                self._run_webview_ui()
                return
            except Exception as exc:
                logger.warning("HTML lock shell unavailable, falling back to tkinter: %s", exc)
                if tk is None:
                    self._available = False
                    self._running = False
                    self._ready.set()
                    return
        elif webview is not None:
            logger.info("Skipping pywebview lock shell because UI is not running on the main thread.")

        root = None
        try:
            root = tk.Tk()
            root.title("OneSign Lock")
            root.configure(bg="#0B1320")
            root.attributes("-fullscreen", True)
            root.attributes("-topmost", True)
            root.overrideredirect(True)
            root.protocol("WM_DELETE_WINDOW", lambda: None)
            root.bind("<Alt-F4>", lambda _e: "break")
            root.bind("<Escape>", lambda _e: "break")

            bg_label = tk.Label(root, bg=self._theme["lock_color_primary"])
            bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)

            content = tk.Frame(root, bg=self._theme["lock_color_primary"])
            content.place(relx=0, rely=0, relwidth=1, relheight=1)

            left = tk.Frame(content, bg=self._theme["lock_color_primary"])
            left.place(relx=0, rely=0, relwidth=0.70, relheight=1)

            right = tk.Frame(content, bg=self._theme["lock_color_panel"])
            right.place(relx=0.70, rely=0, relwidth=0.30, relheight=1)

            left_inner = tk.Frame(left, bg=self._theme["lock_color_primary"])
            logo_label = tk.Label(right, bg=self._theme["lock_color_panel"])
            logo_label.place(relx=0.90, rely=0.08, anchor="ne")

            headline = tk.Label(
                left_inner,
                text=self._theme["lock_brand_name"],
                fg=self._theme["lock_color_text"],
                bg=self._theme["lock_color_primary"],
                font=("Segoe UI", 30, "bold"),
                justify="left",
                anchor="w",
            )
            headline.pack(anchor="w")

            helper_var = tk.StringVar(value="Tap your badge or sign in with Windows credentials.")
            helper_lbl = tk.Label(
                left_inner,
                textvariable=helper_var,
                fg=self._theme["lock_color_text"],
                bg=self._theme["lock_color_primary"],
                font=("Segoe UI", 13),
                justify="left",
                anchor="w",
            )
            helper_lbl.pack(anchor="w", pady=(12, 0), fill="x")

            menu_btn = tk.Button(
                left,
                text="☰ Menu",
                font=("Segoe UI", 12, "bold"),
                fg="#FFFFFF",
                bg=self._theme["lock_color_primary"],
                relief="solid",
                borderwidth=1,
                highlightthickness=0,
                activeforeground="#FFFFFF",
                activebackground=self._theme["lock_color_primary"],
                cursor="hand2",
            )
            menu_btn.place(relx=0.06, rely=0.94, anchor="sw")

            panel_title = tk.Label(
                right,
                text="OneSign",
                fg=self._theme["lock_color_text"],
                bg=self._theme["lock_color_panel"],
                font=("Segoe UI", 24, "bold"),
                anchor="w",
                justify="left",
            )
            panel_title.place(relx=0.12, rely=0.28, anchor="nw")

            panel_message_var = tk.StringVar(value="Welcome back.\nSingle Sign On is ready when you are.")
            panel_message = tk.Label(
                right,
                textvariable=panel_message_var,
                fg=self._theme["lock_color_text"],
                bg=self._theme["lock_color_panel"],
                font=("Segoe UI", 12),
                anchor="nw",
                justify="left",
            )
            panel_message.place(relx=0.12, rely=0.37, anchor="nw", relwidth=0.76)

            workstation_var = tk.StringVar(value="Computer: Unknown")
            workstation_lbl = tk.Label(
                right,
                textvariable=workstation_var,
                fg=self._theme["lock_color_text"],
                bg=self._theme["lock_color_panel"],
                font=("Segoe UI", 12),
                anchor="se",
                justify="right",
            )
            workstation_lbl.place(relx=0.95, rely=0.95, anchor="se")

            hex_canvas = tk.Canvas(left_inner, highlightthickness=0, bd=0)
            hex_canvas.pack(fill="x", pady=(34, 26))

            login_frame = tk.Frame(left_inner, bg=self._theme["lock_color_primary"])
            login_frame.pack(fill="x")
            login_frame.grid_columnconfigure(0, weight=1)
            login_frame.grid_columnconfigure(1, weight=1)

            username_var = tk.StringVar()
            password_var = tk.StringVar()
            username_entry = tk.Entry(
                login_frame,
                textvariable=username_var,
                font=("Segoe UI", 12),
                relief="flat",
                bg=self._theme["lock_color_hex"],
                fg="#1D2A43",
                insertbackground="#1D2A43",
            )
            username_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10), ipady=10)

            password_entry = tk.Entry(
                login_frame,
                textvariable=password_var,
                font=("Segoe UI", 12),
                relief="flat",
                show="•",
                bg=self._theme["lock_color_hex"],
                fg="#1D2A43",
                insertbackground="#1D2A43",
            )
            password_entry.grid(row=0, column=1, sticky="ew", ipady=10)

            submit_btn = tk.Button(
                left_inner,
                text="Unlock",
                font=("Segoe UI", 11, "bold"),
                bg=self._theme["lock_color_panel"],
                fg="#FFFFFF",
                relief="flat",
                cursor="hand2",
                padx=24,
                pady=10,
            )
            submit_btn.pack(anchor="w", pady=(18, 0))

            status_var = tk.StringVar(value="Ready to unlock.")
            status_lbl = tk.Label(
                left_inner,
                textvariable=status_var,
                fg=self._theme["lock_color_text"],
                bg=self._theme["lock_color_primary"],
                font=("Segoe UI", 11),
                anchor="w",
                justify="left",
            )
            status_lbl.pack(anchor="w", fill="x", pady=(16, 0))
            status_title_var = tk.StringVar(value="")
            status_title_lbl = tk.Label(
                left_inner,
                textvariable=status_title_var,
                fg=self._theme["lock_color_text"],
                bg=self._theme["lock_color_primary"],
                font=("Segoe UI", 16, "bold"),
                anchor="w",
                justify="left",
            )
            status_title_lbl.pack(anchor="w", fill="x", pady=(12, 0))
            loader_var = tk.StringVar(value="")
            loader_lbl = tk.Label(
                left_inner,
                textvariable=loader_var,
                fg=self._theme["lock_color_text"],
                bg=self._theme["lock_color_primary"],
                font=("Segoe UI", 11),
                anchor="w",
                justify="left",
            )
            loader_lbl.pack(anchor="w", fill="x", pady=(6, 0))

            bg_image_ref = None
            logo_image_ref = None
            success_after_ids: list[str] = []
            loader_after_id: str | None = None
            loader_states = {"locking", "authenticating", "success"}
            spinner = itertools.cycle(("", ".", "..", "..."))
            current_loader_state = "ready"

            def _hex_points(cx: float, cy: float, size: float) -> list[float]:
                return [
                    cx - size * 0.56, cy - size,
                    cx + size * 0.56, cy - size,
                    cx + size, cy,
                    cx + size * 0.56, cy + size,
                    cx - size * 0.56, cy + size,
                    cx - size, cy,
                ]

            def _clear_success_timers():
                nonlocal success_after_ids
                for after_id in success_after_ids:
                    try:
                        root.after_cancel(after_id)
                    except Exception:
                        pass
                success_after_ids = []

            def _set_form_state(state: str):
                username_entry.configure(state=state)
                password_entry.configure(state=state)
                submit_btn.configure(state=state, cursor="hand2" if state == "normal" else "")

            def _draw_hexagons():
                hex_canvas.delete("all")
                hex_bg = self._theme["lock_color_hex"]
                text_fg = "#20304F"
                hex_canvas.configure(bg=self._theme["lock_color_primary"])
                width = max(320, hex_canvas.winfo_width())
                height = max(220, hex_canvas.winfo_height())
                size = max(44, min(width * 0.11, height * 0.24))
                left_x = max(size + 16, width * 0.28)
                top_y = height * 0.34
                bottom_y = top_y + size * 1.62
                bottom_x = left_x + size * 0.42

                title_font = ("Segoe UI", max(11, int(size * 0.24)), "bold")
                body_font = ("Segoe UI", max(9, int(size * 0.15)))
                icon_font = ("Segoe UI Emoji", max(20, int(size * 0.42)))

                tiles = [
                    (left_x, top_y, "🪪", "Tap badge", "Fast access"),
                    (bottom_x, bottom_y, "🔓", "Type username", "Secure sign in"),
                ]
                for cx, cy, icon, title, subtitle in tiles:
                    hex_canvas.create_polygon(_hex_points(cx, cy, size), fill=hex_bg, outline=hex_bg)
                    hex_canvas.create_text(cx, cy - size * 0.28, text=icon, fill=text_fg, font=icon_font)
                    hex_canvas.create_text(cx, cy + size * 0.10, text=title, fill=text_fg, font=title_font)
                    hex_canvas.create_text(cx, cy + size * 0.42, text=subtitle, fill="#4B6286", font=body_font)

            def _layout_shell():
                width = max(1, root.winfo_width())
                height = max(1, root.winfo_height())
                left_width = int(width * 0.68)
                inner_width = min(max(int(left_width * 0.62), 420), 760)
                inner_x = max(44, (left_width - inner_width) // 2)
                inner_y = max(60, int(height * 0.14))
                inner_height = max(320, int(height * 0.62))
                left_inner.place(x=inner_x, y=inner_y, width=inner_width, height=inner_height)
                helper_lbl.configure(wraplength=max(240, inner_width - 20))
                status_lbl.configure(wraplength=max(240, inner_width - 20))
                status_title_lbl.configure(wraplength=max(240, inner_width - 20))
                panel_message.configure(wraplength=max(160, int(width * 0.20)))
                hex_canvas.configure(height=max(220, min(340, int(inner_width * 0.46))))
                _draw_hexagons()

            def _update_colors():
                content.configure(bg=self._theme["lock_color_primary"])
                left.configure(bg=self._theme["lock_color_primary"])
                right.configure(bg=self._theme["lock_color_panel"])
                bg_label.configure(bg=self._theme["lock_color_primary"])
                headline.configure(bg=self._theme["lock_color_primary"], fg=self._theme["lock_color_text"], text=self._theme["lock_brand_name"])
                helper_lbl.configure(bg=self._theme["lock_color_primary"], fg=self._theme["lock_color_text"])
                menu_btn.configure(bg=self._theme["lock_color_primary"], activebackground=self._theme["lock_color_primary"])
                panel_title.configure(bg=self._theme["lock_color_panel"], fg=self._theme["lock_color_text"])
                panel_message.configure(bg=self._theme["lock_color_panel"], fg=self._theme["lock_color_text"])
                workstation_lbl.configure(bg=self._theme["lock_color_panel"], fg=self._theme["lock_color_text"])
                status_lbl.configure(bg=self._theme["lock_color_primary"], fg=self._theme["lock_color_text"])
                status_title_lbl.configure(bg=self._theme["lock_color_primary"], fg=self._theme["lock_color_text"])
                loader_lbl.configure(bg=self._theme["lock_color_primary"], fg=self._theme["lock_color_text"])
                login_frame.configure(bg=self._theme["lock_color_primary"])
                username_entry.configure(bg=self._theme["lock_color_hex"])
                password_entry.configure(bg=self._theme["lock_color_hex"])
                submit_btn.configure(bg=self._theme["lock_color_panel"])
                _layout_shell()

            def _stop_loader():
                nonlocal loader_after_id
                if loader_after_id:
                    try:
                        root.after_cancel(loader_after_id)
                    except Exception:
                        pass
                    loader_after_id = None
                loader_var.set("")

            def _start_loader():
                nonlocal loader_after_id
                _stop_loader()

                def _tick():
                    nonlocal loader_after_id
                    if current_loader_state not in loader_states:
                        loader_after_id = None
                        return
                    loader_var.set(f"Loading{next(spinner)}")
                    loader_after_id = root.after(350, _tick)

                _tick()

            def _set_stage(state: str, title: str = "", message: str = ""):
                nonlocal current_loader_state
                current_loader_state = state
                status_title_var.set(title)
                status_lbl.configure(font=("Segoe UI", 11, "bold" if state in loader_states else "normal"))
                status_var.set(message)
                if state in loader_states:
                    _start_loader()
                else:
                    _stop_loader()

            def _resolve_local_image(source: str) -> Path | None:
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

            def _resolve_remote_image(source: str) -> str | None:
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

            def _load_image_source(source: str, target: str):
                if not source or Image is None or ImageTk is None or ImageOps is None:
                    self._queue.put(("image_result", (target, None)))
                    return
                try:
                    local_path = _resolve_local_image(source)
                    if local_path is not None:
                        img = Image.open(local_path).convert("RGBA")
                        self._queue.put(("image_result", (target, img)))
                        return
                    remote_url = _resolve_remote_image(source)
                    if not remote_url:
                        self._queue.put(("image_result", (target, None)))
                        return
                    resp = requests.get(remote_url, timeout=12)
                    resp.raise_for_status()
                    img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                    self._queue.put(("image_result", (target, img)))
                except Exception:
                    self._queue.put(("image_result", (target, None)))

            def _refresh_remote_images():
                threading.Thread(
                    target=_load_image_source,
                    args=(str(self._theme.get("lock_background_image", "")), "background"),
                    daemon=True,
                ).start()
                threading.Thread(
                    target=_load_image_source,
                    args=(str(self._theme.get("lock_logo_image", "")), "logo"),
                    daemon=True,
                ).start()

            def _on_password_submit(_evt=None):
                username = username_var.get().strip()
                password = password_var.get()
                if not username or not password:
                    status_var.set("Enter both username and password.")
                    return "break"
                _clear_success_timers()
                _set_form_state("disabled")
                _set_stage("authenticating", "", "Authenticating user, loading workspace...")
                helper_var.set("Verifying your credentials with OneSign.")
                if callable(self._on_password_login):
                    threading.Thread(target=self._on_password_login, args=(username, password), daemon=True).start()
                return "break"

            username_entry.bind("<Return>", _on_password_submit)
            submit_btn.configure(command=_on_password_submit)
            password_entry.bind("<Return>", _on_password_submit)
            menu_btn.configure(command=lambda: threading.Thread(target=self._on_lock_requested, daemon=True).start() if callable(self._on_lock_requested) else None)

            def _apply_resized_background(pil_image):
                nonlocal bg_image_ref
                if pil_image is None or ImageTk is None or ImageOps is None:
                    bg_label.configure(image="", bg=self._theme["lock_color_primary"])
                    bg_image_ref = None
                    return
                width = max(1, root.winfo_width())
                height = max(1, root.winfo_height())
                fitted = ImageOps.fit(pil_image, (width, height), method=Image.LANCZOS)
                bg_image_ref = ImageTk.PhotoImage(fitted)
                bg_label.configure(image=bg_image_ref)

            def _apply_logo(pil_image):
                nonlocal logo_image_ref
                if pil_image is None or ImageTk is None:
                    logo_label.configure(image="", text="")
                    logo_image_ref = None
                    return
                max_w, max_h = 180, 80
                ratio = min(max_w / pil_image.width, max_h / pil_image.height, 1.0)
                resized = pil_image.resize((max(1, int(pil_image.width * ratio)), max(1, int(pil_image.height * ratio))), Image.LANCZOS)
                logo_image_ref = ImageTk.PhotoImage(resized)
                logo_label.configure(image=logo_image_ref)

            cached_bg = None
            cached_logo = None

            def _reset_form(workstation: str):
                _clear_success_timers()
                _set_form_state("normal")
                username_var.set("")
                password_var.set("")
                helper_var.set("Locking workstation...")
                _set_stage("locking", "", "Locking workstation...")
                panel_message_var.set("Welcome back.\nSingle Sign On is ready when you are.")
                workstation_var.set(f"Computer: {workstation}")
                _layout_shell()
                success_after_ids.append(root.after(900, lambda: _set_stage("ready", "", "Ready to unlock.")))
                success_after_ids.append(root.after(900, lambda: helper_var.set("Tap your badge or sign in with Windows credentials.")))
                success_after_ids.append(root.after(900, username_entry.focus_set))

            def _begin_success_state(display_name: str):
                _clear_success_timers()
                _set_form_state("disabled")
                helper_var.set("Authentication complete.")
                _set_stage("success", f"Welcome, {display_name}", "Authenticating user, loading workspace...")
                panel_message_var.set("Authenticating user, loading workspace...")
                success_after_ids.append(root.after(1800, lambda: self._queue.put(("hide", ()))))

            def _on_resize(_evt=None):
                _layout_shell()
                if cached_bg is not None:
                    _apply_resized_background(cached_bg)

            root.bind("<Configure>", _on_resize)
            _update_colors()
            _refresh_remote_images()
            root.withdraw()

            def pump():
                nonlocal cached_bg, cached_logo
                try:
                    while True:
                        command, args = self._queue.get_nowait()
                        if command == "show_lock":
                            workstation = args[0]
                            _reset_form(workstation)
                            root.deiconify()
                            root.lift()
                            root.focus_force()
                        elif command == "hide":
                            _clear_success_timers()
                            _stop_loader()
                            root.withdraw()
                        elif command == "theme":
                            payload = args[0] or {}
                            self._theme.update(payload)
                            _update_colors()
                            _refresh_remote_images()
                        elif command == "auth_failed":
                            message = args[0] or "Authentication failed."
                            _clear_success_timers()
                            _set_form_state("normal")
                            helper_var.set("Tap your badge or sign in with Windows credentials.")
                            _set_stage("failed", "", message)
                            password_var.set("")
                            password_entry.focus_set()
                        elif command == "auth_success":
                            _begin_success_state(args[0] or "User")
                        elif command == "image_result":
                            target, image = args
                            if target == "background":
                                cached_bg = image
                                _apply_resized_background(cached_bg)
                            elif target == "logo":
                                cached_logo = image
                                _apply_logo(cached_logo)
                        elif command == "stop":
                            root.destroy()
                            return
                except queue.Empty:
                    pass
                root.after(150, pump)

            self._ready.set()
            pump()
            root.mainloop()
        except Exception as exc:
            logger.warning("Fullscreen lock shell unavailable: %s", exc)
            self._available = False
        finally:
            self._running = False
            self._ready.set()
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass

    def notify_auth_failed(self, message: str):
        if not self._available or not self._running:
            return
        self._queue.put(("auth_failed", (message,)))
