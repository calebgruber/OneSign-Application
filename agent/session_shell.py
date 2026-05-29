import io
import logging
import queue
import threading
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
        self._available = tk is not None
        self._theme = {
            "lock_background_image": "",
            "lock_logo_image": "",
            "lock_server_base_url": "",
            "lock_brand_name": "Secure log in",
            "lock_color_primary": "#2B4D89",
            "lock_color_panel": "#1D2A43",
            "lock_color_hex": "#F4F6FA",
            "lock_color_text": "#FFFFFF",
        }

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
        self._thread = threading.Thread(target=self._run_ui, daemon=True, name="OneSign-SessionShell")
        self._thread.start()
        self._ready.wait(timeout=5)

    def _run_ui(self):
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

            bg_image_ref = None
            logo_image_ref = None
            success_after_ids: list[str] = []

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
                left_x = max(size + 16, width * 0.22)
                top_y = height * 0.34
                bottom_y = top_y + size * 1.75
                right_x = left_x + size * 1.85
                right_y = (top_y + bottom_y) / 2

                title_font = ("Segoe UI", max(11, int(size * 0.24)), "bold")
                body_font = ("Segoe UI", max(9, int(size * 0.15)))
                icon_font = ("Segoe UI Emoji", max(20, int(size * 0.42)))

                tiles = [
                    (left_x, top_y, "🪪", "Tap Badge", "Fast access"),
                    (left_x, bottom_y, "🔐", "Unlock", "Secure session"),
                    (right_x, right_y, "💻", "SSO Ready", "Windows sign-in"),
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
                login_frame.configure(bg=self._theme["lock_color_primary"])
                username_entry.configure(bg=self._theme["lock_color_hex"])
                password_entry.configure(bg=self._theme["lock_color_hex"])
                submit_btn.configure(bg=self._theme["lock_color_panel"])
                _layout_shell()

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
                status_var.set("Authenticating…")
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
                helper_var.set("Tap your badge or sign in with Windows credentials.")
                status_var.set("Ready to unlock.")
                panel_message_var.set("Welcome back.\nSingle Sign On is ready when you are.")
                workstation_var.set(f"Computer: {workstation}")
                _layout_shell()
                username_entry.focus_set()

            def _begin_success_state(display_name: str):
                _clear_success_timers()
                _set_form_state("disabled")
                helper_var.set("Authentication complete.")
                status_var.set(f"Welcome, {display_name}")
                panel_message_var.set("Loading your secure workspace…")
                success_after_ids.append(root.after(700, lambda: status_var.set("Loading your workspace…")))
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
                            status_var.set(message)
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
