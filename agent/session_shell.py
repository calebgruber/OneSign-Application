import io
import logging
import queue
import threading
from typing import Callable

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

            logo_label = tk.Label(right, bg=self._theme["lock_color_panel"])
            logo_label.place(relx=0.95, rely=0.05, anchor="ne")

            headline = tk.Label(
                left,
                text=self._theme["lock_brand_name"],
                fg=self._theme["lock_color_text"],
                bg=self._theme["lock_color_primary"],
                font=("Segoe UI", 28, "bold"),
                justify="left",
                anchor="w",
            )
            headline.place(relx=0.10, rely=0.46, anchor="w")

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

            status_var = tk.StringVar(value="Tap ID card or enter username.")
            status_lbl = tk.Label(
                left,
                textvariable=status_var,
                fg=self._theme["lock_color_text"],
                bg=self._theme["lock_color_primary"],
                font=("Segoe UI", 11),
                anchor="w",
            )
            status_lbl.place(relx=0.10, rely=0.62, anchor="w")

            username_var = tk.StringVar()
            password_var = tk.StringVar()
            hex_canvas = tk.Canvas(left, width=430, height=430, highlightthickness=0, bd=0)
            hex_canvas.place(relx=0.10, rely=0.18, anchor="nw")

            username_entry = tk.Entry(
                left,
                textvariable=username_var,
                font=("Segoe UI", 12),
                relief="flat",
                justify="center",
                bg=self._theme["lock_color_hex"],
                fg="#1D2A43",
            )
            password_entry = tk.Entry(
                left,
                textvariable=password_var,
                font=("Segoe UI", 12),
                relief="flat",
                justify="center",
                show="•",
                bg=self._theme["lock_color_hex"],
                fg="#1D2A43",
            )
            submit_btn = tk.Button(
                left,
                text="Enter",
                font=("Segoe UI", 10, "bold"),
                bg=self._theme["lock_color_panel"],
                fg="#FFFFFF",
                relief="flat",
                cursor="hand2",
            )

            bg_image_ref = None
            logo_image_ref = None
            icon_refs: dict[str, int] = {}

            def _hex_points(cx: float, cy: float, size: float) -> list[float]:
                return [
                    cx - size * 0.56, cy - size,
                    cx + size * 0.56, cy - size,
                    cx + size, cy,
                    cx + size * 0.56, cy + size,
                    cx - size * 0.56, cy + size,
                    cx - size, cy,
                ]

            def _place_login_widgets():
                if password_var.get():
                    password_entry.place(x=54, y=214, width=152, height=28)
                    submit_btn.place(x=213, y=214, width=56, height=28)
                    username_entry.place_forget()
                    icon_refs["input"] = hex_canvas.create_text(
                        162, 206, text="🔒", fill="#20304F", font=("Segoe UI Emoji", 22)
                    )
                else:
                    username_entry.place(x=76, y=214, width=152, height=28)
                    password_entry.place_forget()
                    submit_btn.place_forget()
                    icon_refs["input"] = hex_canvas.create_text(
                        162, 206, text="👤", fill="#20304F", font=("Segoe UI Emoji", 22)
                    )

            def _draw_hexagons():
                for item in hex_canvas.find_all():
                    hex_canvas.delete(item)
                icon_refs.clear()

                hex_bg = self._theme["lock_color_hex"]
                text_fg = "#20304F"
                hex_canvas.configure(bg=self._theme["lock_color_primary"])

                hex_canvas.create_polygon(_hex_points(110, 105, 55), fill=hex_bg, outline=hex_bg)
                hex_canvas.create_polygon(_hex_points(110, 215, 55), fill=hex_bg, outline=hex_bg)
                hex_canvas.create_polygon(_hex_points(230, 160, 55), fill=hex_bg, outline=hex_bg)

                hex_canvas.create_text(110, 84, text="🪪", fill=text_fg, font=("Segoe UI Emoji", 22))
                hex_canvas.create_text(110, 113, text="Badge Tap", fill=text_fg, font=("Segoe UI", 12, "bold"))

                hex_canvas.create_text(230, 138, text="🧾", fill=text_fg, font=("Segoe UI Emoji", 22))
                hex_canvas.create_text(230, 168, text="ID Card", fill=text_fg, font=("Segoe UI", 12, "bold"))

                if username_var.get() and not password_var.get():
                    hex_canvas.create_text(110, 242, text="Press Enter for password", fill="#445A7E", font=("Segoe UI", 9))
                else:
                    hex_canvas.create_text(110, 242, text="Enter credentials", fill="#445A7E", font=("Segoe UI", 9))
                _place_login_widgets()

            def _update_colors():
                content.configure(bg=self._theme["lock_color_primary"])
                left.configure(bg=self._theme["lock_color_primary"])
                right.configure(bg=self._theme["lock_color_panel"])
                bg_label.configure(bg=self._theme["lock_color_primary"])
                headline.configure(bg=self._theme["lock_color_primary"], fg=self._theme["lock_color_text"], text=self._theme["lock_brand_name"])
                menu_btn.configure(bg=self._theme["lock_color_primary"], activebackground=self._theme["lock_color_primary"])
                workstation_lbl.configure(bg=self._theme["lock_color_panel"], fg=self._theme["lock_color_text"])
                status_lbl.configure(bg=self._theme["lock_color_primary"], fg=self._theme["lock_color_text"])
                username_entry.configure(bg=self._theme["lock_color_hex"])
                password_entry.configure(bg=self._theme["lock_color_hex"])
                submit_btn.configure(bg=self._theme["lock_color_panel"])
                _draw_hexagons()

            def _load_image_from_url(url: str, target: str):
                if not url or Image is None or ImageTk is None or ImageOps is None:
                    self._queue.put(("image_result", (target, None)))
                    return
                try:
                    resp = requests.get(url, timeout=12)
                    if resp.status_code != 200:
                        self._queue.put(("image_result", (target, None)))
                        return
                    img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                    self._queue.put(("image_result", (target, img)))
                except Exception:
                    self._queue.put(("image_result", (target, None)))

            def _refresh_remote_images():
                threading.Thread(
                    target=_load_image_from_url,
                    args=(str(self._theme.get("lock_background_image", "")), "background"),
                    daemon=True,
                ).start()
                threading.Thread(
                    target=_load_image_from_url,
                    args=(str(self._theme.get("lock_logo_image", "")), "logo"),
                    daemon=True,
                ).start()

            def _on_username_submit(_evt=None):
                if not username_var.get().strip():
                    return "break"
                password_var.set("")
                status_var.set("Enter password and press Enter.")
                _draw_hexagons()
                password_entry.focus_set()
                return "break"

            def _on_password_submit(_evt=None):
                username = username_var.get().strip()
                password = password_var.get()
                if not username or not password:
                    return "break"
                status_var.set("Authenticating…")
                if callable(self._on_password_login):
                    threading.Thread(target=self._on_password_login, args=(username, password), daemon=True).start()
                return "break"

            username_entry.bind("<Return>", _on_username_submit)
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
                username_var.set("")
                password_var.set("")
                status_var.set("Tap ID card or enter username.")
                workstation_var.set(f"Computer: {workstation}")
                _draw_hexagons()
                username_entry.focus_set()

            def _on_resize(_evt=None):
                if cached_bg is not None:
                    _apply_resized_background(cached_bg)

            root.bind("<Configure>", _on_resize)
            _draw_hexagons()
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
                            root.withdraw()
                        elif command == "theme":
                            payload = args[0] or {}
                            self._theme.update(payload)
                            _update_colors()
                            _refresh_remote_images()
                        elif command == "auth_failed":
                            message = args[0] or "Authentication failed."
                            status_var.set(message)
                            password_var.set("")
                            _draw_hexagons()
                            password_entry.focus_set()
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
