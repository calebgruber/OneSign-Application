"""
win_login.py — Windows workstation lock/unlock helpers.

Approaches used:
  - Lock:   user32.LockWorkStation()
  - Unlock: Sends credentials to the Winlogon/default desktop via
            SendKeys through the secure desktop using SSPI / credential
            provider simulation.

NOTE: The most reliable production approach for automatically unlocking a
locked Windows workstation programmatically (without an installed credential
provider) is to use the Windows "SendInput" API on the Winlogon desktop.
This requires the process to run as SYSTEM and switch desktop context.

For environments that want seamless SSO, a custom Windows Credential
Provider DLL is the gold-standard. This module implements the
"switch-to-secure-desktop + SendInput" approach which works well when
the standard Windows Logon UI is present.
"""

import ctypes
import ctypes.wintypes
import json
import logging
import shlex
import struct
import subprocess
import time

logger = logging.getLogger(__name__)

ONESIGN_PIPE_NAME = r"\\.\pipe\OneSignCredProvider"

# ── Win32 constants ─────────────────────────────────────────────────────────
WM_KEYDOWN      = 0x0100
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP   = 0x0002
INPUT_KEYBOARD    = 1
VK_RETURN       = 0x0D
VK_TAB          = 0x09
VK_LCONTROL     = 0xA2
VK_LMENU        = 0xA4
VK_DELETE       = 0x2E

# ── ctypes structures ────────────────────────────────────────────────────────
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.wintypes.WORD),
        ("wScan",       ctypes.wintypes.WORD),
        ("dwFlags",     ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type",    ctypes.wintypes.DWORD),
        ("_union",  _INPUT_UNION),
    ]

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]


# ── helpers ──────────────────────────────────────────────────────────────────

def _send_vk(vk: int, flags: int = 0):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp._union.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _send_unicode_char(ch: str):
    scan = ord(ch)
    inp_down = INPUT(type=INPUT_KEYBOARD)
    inp_down._union.ki = KEYBDINPUT(
        wVk=0, wScan=scan, dwFlags=KEYEVENTF_UNICODE, time=0
    )
    inp_up = INPUT(type=INPUT_KEYBOARD)
    inp_up._union.ki = KEYBDINPUT(
        wVk=0, wScan=scan, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0
    )
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp_up),   ctypes.sizeof(INPUT))


def _type_string(text: str, delay_ms: int = 20):
    for ch in text:
        _send_unicode_char(ch)
        time.sleep(delay_ms / 1000.0)


def unlock_via_credential_provider_pipe(username: str, password: str, domain: str = '.') -> bool:
    r"""
    Send credentials to the OneSign Windows Credential Provider DLL via
    the named pipe \\.\pipe\OneSignCredProvider.

    The credential provider (if installed and running in LogonUI) reads the
    JSON payload and submits credentials to Windows through the proper
    ICredentialProvider::GetSerialization path, which is the most reliable
    and secure unlock mechanism.

    Returns True if the message was successfully written to the pipe.
    A True return does NOT guarantee the workstation unlocked — it means
    the credentials were handed off to the provider DLL successfully.
    """
    payload = json.dumps({
        "username": username,
        "password": password,
        "domain": domain,
    }).encode("utf-8")
    # 4-byte little-endian length prefix followed by JSON body
    message = struct.pack("<I", len(payload)) + payload

    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = ctypes.wintypes.HANDLE(-1).value

    try:
        h = ctypes.windll.kernel32.CreateFileW(
            ONESIGN_PIPE_NAME,
            GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if h == INVALID_HANDLE_VALUE:
            err = ctypes.GetLastError()
            logger.debug("Credential provider pipe not available (err=%d); will use SendInput fallback", err)
            return False

        written = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.WriteFile(
            h,
            message,
            len(message),
            ctypes.byref(written),
            None,
        )
        ctypes.windll.kernel32.CloseHandle(h)

        if ok and written.value == len(message):
            logger.info("Credentials sent to OneSign credential provider pipe for user '%s'", username)
            return True

        logger.debug("Pipe write incomplete (wrote %d/%d bytes)", written.value, len(message))
        return False
    except Exception as exc:
        logger.debug("Credential provider pipe error: %s", exc)
        return False



def lock_workstation() -> bool:
    """Lock the current Windows session."""
    result = ctypes.windll.user32.LockWorkStation()
    if result:
        logger.info("Workstation locked")
        return True
    logger.warning("LockWorkStation() failed (err=%d)", ctypes.GetLastError())
    return False


def is_workstation_locked() -> bool:
    """
    Heuristic: try to open the 'Default' desktop — if it fails or
    the active desktop is 'Winlogon' / 'Screen-saver', the machine is locked.
    """
    try:
        # OpenInputDesktop returns 0 if no interactive desktop is accessible
        hDesk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_READOBJECTS
        if not hDesk:
            return True
        # Get desktop name
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetUserObjectInformationW(
            hDesk, 2, buf, ctypes.sizeof(buf), None
        )
        ctypes.windll.user32.CloseDesktop(hDesk)
        name = buf.value.lower()
        logger.debug("Active desktop: %s", name)
        return name in ('winlogon', 'screen-saver', '')
    except Exception as exc:
        logger.debug("is_workstation_locked error: %s", exc)
        return False


def unlock_workstation(username: str, password: str, domain: str = '.') -> bool:
    """
    Attempt to unlock a locked Windows workstation by switching to the
    Winlogon desktop and sending credential keystrokes.

    This works when:
    - The process is running as SYSTEM (Windows service).
    - The lock screen is the standard Windows Credential UI.

    Parameters
    ----------
    username : str  — Windows username (SAM or UPN format)
    password : str  — Windows password
    domain   : str  — '.' for local account, or NETBIOS domain name

    Returns True if keystrokes were sent without error.
    """
    try:
        # 1. Open the Winlogon desktop
        h_winlogon = ctypes.windll.user32.OpenDesktopW(
            "Winlogon", 0, False,
            0x0200 | 0x0100 | 0x0080  # DESKTOP_WRITEOBJECTS | DESKTOP_READOBJECTS | DESKTOP_SWITCHDESKTOP
        )
        if not h_winlogon:
            logger.warning("Could not open Winlogon desktop (err=%d)", ctypes.GetLastError())
            return False

        # 2. Switch our thread to the Winlogon desktop
        ctypes.windll.user32.SetThreadDesktop(h_winlogon)

        # 3. Send Ctrl+Alt+Del simulation (only works on physical console session)
        # The proper way is via WTSSendMessage or credential provider.
        # As a best-effort, send a click to dismiss the lock screen first:
        time.sleep(0.3)
        _send_vk(VK_RETURN)  # dismiss screensaver / wake screen
        time.sleep(0.5)

        # 4. Type credentials
        _type_string(username)
        time.sleep(0.1)
        _send_vk(VK_TAB)
        time.sleep(0.1)
        _type_string(password)
        time.sleep(0.1)
        _send_vk(VK_RETURN)

        # 5. Switch back to our original desktop
        h_default = ctypes.windll.user32.OpenDesktopW("Default", 0, False, 0x0200 | 0x0100)
        if h_default:
            ctypes.windll.user32.SetThreadDesktop(h_default)
            ctypes.windll.user32.CloseDesktop(h_default)
        ctypes.windll.user32.CloseDesktop(h_winlogon)

        logger.info("Unlock keystrokes sent for user '%s'", username)
        return True

    except Exception as exc:
        logger.error("unlock_workstation error: %s", exc, exc_info=True)
        return False


def validate_windows_credentials(username: str, password: str, domain: str = '.') -> bool:
    """
    Validate provided Windows credentials using LogonUserW.

    This allows local credential checks while the OneSign lock overlay is shown.
    """
    user = (username or "").strip()
    pwd = password or ""
    dom = (domain or ".").strip() or "."
    if not user or not pwd:
        return False

    handle = ctypes.wintypes.HANDLE()
    LOGON32_LOGON_NETWORK = 3
    LOGON32_PROVIDER_DEFAULT = 0
    ok = ctypes.windll.advapi32.LogonUserW(
        user,
        dom,
        pwd,
        LOGON32_LOGON_NETWORK,
        LOGON32_PROVIDER_DEFAULT,
        ctypes.byref(handle),
    )
    if not ok:
        return False
    try:
        return True
    finally:
        try:
            ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            pass


def get_idle_seconds() -> float:
    """
    Return workstation idle seconds using GetLastInputInfo.
    """
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    tick_now = ctypes.windll.kernel32.GetTickCount()
    idle_ms = max(0, int(tick_now) - int(info.dwTime))
    return idle_ms / 1000.0


def unlock_with_credential_provider(
    provider_command: str,
    username: str,
    password: str,
    domain: str = '.',
    timeout_seconds: int = 20,
) -> bool:
    """
    Unlock workstation by invoking an external credential provider helper.

    The helper is expected to read a JSON payload from stdin and return exit
    code 0 on success.
    """
    cmd = (provider_command or '').strip()
    if not cmd:
        logger.warning("Credential provider command is empty")
        return False

    try:
        result = subprocess.run(
            shlex.split(cmd, posix=False),
            input=json.dumps({
                "username": username,
                "password": password,
                "domain": domain,
            }),
            text=True,
            capture_output=True,
            timeout=max(1, int(timeout_seconds)),
            check=False,
        )
    except Exception as exc:
        logger.error("Credential provider invocation failed: %s", exc)
        return False

    if result.returncode == 0:
        logger.info("Credential provider unlock succeeded for user '%s'", username)
        return True

    logger.warning(
        "Credential provider unlock failed (code=%s): %s",
        result.returncode,
        (result.stderr or result.stdout or '').strip()[:300],
    )
    return False


def sign_in_new_session(username: str, password: str, domain: str = '.') -> bool:
    """
    Trigger a new Windows logon session at the logon screen
    (machine not yet logged in, or after a sign-out).

    Uses the same Winlogon desktop approach.
    """
    return unlock_workstation(username, password, domain)
