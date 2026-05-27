"""
pcprox.py — ctypes wrapper for the RF Ideas pcProx Plus DLL.

Supported DLL:
  32-bit: pcProxAPI.dll
  64-bit: pcProxAPI64.dll  (default)

Key API calls used:
  USBConnect(long *pDevID)   → 1 on success
  GetActiveID(BYTE *pData, BYTE bSize) → bytes read (0 if no card)
  USBDisconnect()
  SetDevTypeSrch(BYTE bDevType)   — 0=pcProx, 1=Airborn, 2=pcProxS
  SetConnectProduct(BYTE bProd)   — 0=USB HID, 1=CDC
"""

import ctypes
import logging
import os
import platform
import time

logger = logging.getLogger(__name__)

# Default DLL locations
_DEFAULT_DLL_64 = r"C:\Program Files\RF IDeas\pcProx\pcProxAPI64.dll"
_DEFAULT_DLL_32 = r"C:\Program Files\RF IDeas\pcProx\pcProxAPI.dll"

CARD_DATA_LEN = 8  # standard card ID byte length


class PcProxError(Exception):
    pass


class PcProxReader:
    """
    Thread-safe wrapper around the pcProx DLL.

    Usage:
        reader = PcProxReader(dll_path=r"C:\\path\\to\\pcProxAPI64.dll")
        reader.connect()
        while True:
            card_id = reader.get_active_id()
            if card_id:
                print("Card:", card_id.hex().upper())
            time.sleep(0.25)
        reader.disconnect()
    """

    def __init__(self, dll_path: str = None):
        if dll_path:
            self._dll_path = dll_path
        elif platform.architecture()[0] == '64bit':
            self._dll_path = _DEFAULT_DLL_64
        else:
            self._dll_path = _DEFAULT_DLL_32

        self._lib = None
        self._dev_id = ctypes.c_long(0)
        self._connected = False

    # ── Connection ──────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Load DLL and open USB connection. Returns True on success."""
        if not os.path.isfile(self._dll_path):
            raise PcProxError(f"DLL not found: {self._dll_path}")

        try:
            self._lib = ctypes.WinDLL(self._dll_path)
        except OSError as exc:
            raise PcProxError(f"Failed to load DLL: {exc}") from exc

        self._declare_functions()

        # Search for HID device (type 0 = pcProx)
        try:
            self._lib.SetDevTypeSrch(ctypes.c_ubyte(0))
            self._lib.SetConnectProduct(ctypes.c_ubyte(0))
        except AttributeError:
            pass  # older DLL versions may not have these

        result = self._lib.USBConnect(ctypes.byref(self._dev_id))
        if result != 1:
            raise PcProxError(f"USBConnect failed (returned {result})")

        self._connected = True
        logger.info("pcProx reader connected (dev_id=%d)", self._dev_id.value)
        return True

    def disconnect(self):
        """Close USB connection and unload DLL."""
        if self._lib and self._connected:
            try:
                self._lib.USBDisconnect()
            except Exception:
                pass
            self._connected = False
        logger.info("pcProx reader disconnected")

    # ── Card Reading ─────────────────────────────────────────────────────

    def get_active_id(self) -> bytes | None:
        """
        Read card ID bytes.
        Returns bytes (1-8 bytes) when a card is present, None otherwise.
        """
        if not self._connected or not self._lib:
            return None

        buf = (ctypes.c_ubyte * CARD_DATA_LEN)()
        n = self._lib.GetActiveID(buf, ctypes.c_ubyte(CARD_DATA_LEN))

        if n <= 0:
            return None

        # n is the number of significant bytes returned
        card_bytes = bytes(buf[:n])
        if all(b == 0 for b in card_bytes):
            return None

        return card_bytes

    def get_card_hex(self) -> str | None:
        """Return the card ID as an uppercase hex string, or None."""
        raw = self.get_active_id()
        if raw is None:
            return None
        return raw.hex().upper()

    # ── Internal ─────────────────────────────────────────────────────────

    def _declare_functions(self):
        """Set ctypes argtypes/restype for each DLL function."""
        lib = self._lib

        # long USBConnect(long *pDevID)
        lib.USBConnect.argtypes = [ctypes.POINTER(ctypes.c_long)]
        lib.USBConnect.restype  = ctypes.c_long

        # void USBDisconnect(void)
        lib.USBDisconnect.argtypes = []
        lib.USBDisconnect.restype  = None

        # int GetActiveID(BYTE *pData, BYTE bSize)
        lib.GetActiveID.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_ubyte,
        ]
        lib.GetActiveID.restype = ctypes.c_int

        # Optional helpers (not all DLL versions have these)
        for fn in ('SetDevTypeSrch', 'SetConnectProduct'):
            if hasattr(lib, fn):
                getattr(lib, fn).argtypes = [ctypes.c_ubyte]
                getattr(lib, fn).restype  = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    def __repr__(self):
        state = "connected" if self._connected else "disconnected"
        return f"<PcProxReader [{state}] dll={self._dll_path!r}>"
