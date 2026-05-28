import logging
import queue
import threading

try:
    import tkinter as tk
except Exception:  # pragma: no cover - depends on host runtime
    tk = None


logger = logging.getLogger(__name__)


class SessionShell:
    """Fullscreen shell shown for authenticated user sessions."""

    def __init__(self, on_lock_requested=None):
        self._on_lock_requested = on_lock_requested
        self._queue: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._ready = threading.Event()
        self._available = tk is not None

    @property
    def available(self) -> bool:
        return self._available

    def show(self, display_name: str, workstation: str):
        if not self._available:
            return
        self._start_if_needed()
        self._queue.put(("show", (display_name, workstation)))

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
            root.title("OneSign Session")
            root.configure(bg="#0B1320")
            root.attributes("-fullscreen", True)
            root.attributes("-topmost", True)
            root.overrideredirect(True)
            root.protocol("WM_DELETE_WINDOW", lambda: None)
            root.bind("<Alt-F4>", lambda _e: "break")
            root.bind("<Escape>", lambda _e: "break")

            card = tk.Frame(root, bg="#1B263B", padx=40, pady=30)
            card.place(relx=0.5, rely=0.5, anchor="center")

            title = tk.Label(
                card,
                text="OneSign Active Session",
                font=("Segoe UI", 30, "bold"),
                fg="#FFFFFF",
                bg="#1B263B",
            )
            title.pack(pady=(0, 20))

            subtitle_var = tk.StringVar(value="Waiting for authentication...")
            subtitle = tk.Label(
                card,
                textvariable=subtitle_var,
                font=("Segoe UI", 16),
                fg="#D9E4FF",
                bg="#1B263B",
                justify="center",
            )
            subtitle.pack(pady=(0, 30))

            status_var = tk.StringVar(value="Session shell active")
            status = tk.Label(
                card,
                textvariable=status_var,
                font=("Segoe UI", 12),
                fg="#B8C5E0",
                bg="#1B263B",
            )
            status.pack(pady=(0, 20))

            def do_lock():
                if callable(self._on_lock_requested):
                    threading.Thread(target=self._on_lock_requested, daemon=True).start()

            tk.Button(
                card,
                text="Lock / Sign Out",
                command=do_lock,
                font=("Segoe UI", 14, "bold"),
                bg="#F76707",
                fg="#FFFFFF",
                relief="flat",
                padx=30,
                pady=12,
                cursor="hand2",
                activebackground="#DB5E06",
                activeforeground="#FFFFFF",
            ).pack()

            def pump():
                try:
                    while True:
                        command, args = self._queue.get_nowait()
                        if command == "show":
                            display_name, workstation = args
                            subtitle_var.set(f"{display_name}\n{workstation}")
                            status_var.set("Session active — use badge tap or Lock / Sign Out.")
                            root.deiconify()
                            root.lift()
                            root.focus_force()
                        elif command == "hide":
                            root.withdraw()
                        elif command == "stop":
                            root.destroy()
                            return
                except queue.Empty:
                    pass
                root.after(200, pump)

            self._ready.set()
            pump()
            root.mainloop()
        except Exception as exc:
            logger.warning("Fullscreen session shell unavailable: %s", exc)
            self._available = False
        finally:
            self._running = False
            self._ready.set()
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass
