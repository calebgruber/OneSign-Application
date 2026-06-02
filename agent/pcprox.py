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
import sys

logger = logging.getLogger(__name__)

# Default DLL locations
_DEFAULT_DLL_64 = r"C:\Program Files\RF IDeas\pcProx\pcProxAPI64.dll"
_DEFAULT_DLL_32 = r"C:\Program Files\RF IDeas\pcProx\pcProxAPI.dll"

CARD_DATA_LEN = 8  # standard card ID byte length
CARD_DATA32_BUFFER_LEN = 32  # matches RF IDeas readercomm.py sample


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
        self._dll_path = self._resolve_dll_path(dll_path)

        self._lib = None
        self._dev_id = ctypes.c_long(0)
        self._connected = False
        self._usb_connect = None
        self._usb_connect_name = ""
        self._usb_disconnect = None
        self._get_active_id = None
        self._set_dev_type_srch = None
        self._set_connect_product = None
        self._get_dev_cnt = None
        self._set_act_dev = None
        self._get_active_id32 = None
        self._get_part_number_string = None
        self._get_vid_pid_vendor_name = None
        self._get_luid = None
        self._active_device_index = -1

    # ── Connection ──────────────────────────────────────────────────────

    def connect(self, active_device_index: int | None = None) -> bool:
        """Load DLL and open USB connection. Returns True on success."""
        if self._connected:
            if active_device_index is not None:
                self.set_active_device(active_device_index)
            return True

        if not os.path.isfile(self._dll_path):
            raise PcProxError(f"DLL not found: {self._dll_path}")

        try:
            self._lib = ctypes.WinDLL(self._dll_path)
        except OSError as exc:
            raise PcProxError(f"Failed to load DLL: {exc}") from exc

        self._declare_functions()

        self._set_dev_type_search(0)
        result = self._call_usb_connect()
        if result != 1:
            # Fallback: broaden search to both USB and serial, matching RF IDeas sample guidance.
            self._set_dev_type_search(-1)
            result = self._call_usb_connect()
        if result != 1:
            raise PcProxError(f"USBConnect failed (returned {result})")

        target_index = self._active_device_index if active_device_index is None else active_device_index
        if target_index is not None and target_index >= 0:
            self.set_active_device(target_index)

        self._connected = True
        logger.info("pcProx reader connected (dev_id=%d)", self._dev_id.value)
        return True

    def _resolve_dll_path(self, dll_path: str | None) -> str:
        arch64 = platform.architecture()[0] == '64bit'

        configured = (dll_path or '').strip().strip('"')
        if configured:
            if configured.lower().endswith('.exe'):
                logger.warning("Configured reader dll_path points to EXE (%s); ignoring it", configured)
            elif configured.lower().endswith('.dll'):
                return configured
            else:
                logger.warning("Configured reader dll_path is not a DLL (%s); ignoring it", configured)

        base_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
        bundled_64 = os.path.join(base_dir, 'pcProxAPI64.dll')
        bundled_32 = os.path.join(base_dir, 'pcProxAPI.dll')

        if arch64:
            candidates = [bundled_64, bundled_32, _DEFAULT_DLL_64, _DEFAULT_DLL_32]
        else:
            candidates = [bundled_32, bundled_64, _DEFAULT_DLL_32, _DEFAULT_DLL_64]

        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate

        return _DEFAULT_DLL_64 if arch64 else _DEFAULT_DLL_32

    def disconnect(self):
        """Close USB connection and unload DLL."""
        if self._lib and self._connected and self._usb_disconnect is not None:
            try:
                self._usb_disconnect()
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

        card32 = self._read_active_id32()
        if card32:
            return card32

        buf = (ctypes.c_ubyte * CARD_DATA_LEN)()
        n = self._call_get_active_id(buf)

        if n <= 0:
            return None

        # n is the number of significant bytes returned
        card_bytes = bytes(buf[:n])
        if all(b == 0 for b in card_bytes):
            return None

        return card_bytes

    def _read_active_id32(self) -> bytes | None:
        """
        Read ID using GetActiveID32 (same API used by RF IDeas readercomm.py).
        Returns card bytes in the same byte order produced by the sample.
        """
        if self._get_active_id32 is None:
            return None

        raw_buf = (ctypes.c_ubyte * CARD_DATA32_BUFFER_LEN)()
        buffer_size = ctypes.c_short(CARD_DATA32_BUFFER_LEN)

        # readercomm.py sleeps before calling GetActiveID32
        import time
        time.sleep(0.25)

        bits = int(self._get_active_id32(raw_buf, buffer_size))
        if bits <= 0:
            return None

        bytes_to_read = (bits + 7) // 8
        if bytes_to_read < CARD_DATA_LEN:
            bytes_to_read = CARD_DATA_LEN
        if bytes_to_read > CARD_DATA32_BUFFER_LEN:
            bytes_to_read = CARD_DATA32_BUFFER_LEN

        # Match readercomm.py output ordering: each byte is prepended.
        ordered = bytes(reversed(bytes(raw_buf[:bytes_to_read])))
        if not ordered or all(b == 0 for b in ordered):
            return None
        return ordered

    def get_card_hex(self) -> str | None:
        """Return the card ID as an uppercase hex string, or None."""
        raw = self.get_active_id()
        if raw is None:
            return None
        return raw.hex().upper()

    def set_active_device(self, index: int) -> bool:
        self._active_device_index = int(index)
        if self._set_act_dev is None:
            return False
        rc = int(self._set_act_dev(ctypes.c_short(int(index))))
        return rc == 1

    def get_active_device_index(self) -> int:
        return self._active_device_index

    def list_devices(self) -> list[dict]:
        devices: list[dict] = []
        was_connected = self._connected
        if not was_connected:
            self.connect()
        try:
            if self._get_dev_cnt is None or self._set_act_dev is None:
                return devices

            count = int(self._get_dev_cnt())
            for i in range(max(0, count)):
                if int(self._set_act_dev(ctypes.c_short(i))) != 1:
                    continue
                devices.append({
                    "index": i,
                    "part_number": self._read_part_number(),
                    "vid_pid_vendor": self._read_vid_pid_vendor_name(),
                    "luid": self._read_luid(),
                })

            if self._active_device_index >= 0:
                self._set_act_dev(ctypes.c_short(self._active_device_index))
        finally:
            if not was_connected:
                self.disconnect()
        return devices

    # ── Internal ─────────────────────────────────────────────────────────

    def _declare_functions(self):
        """Set ctypes argtypes/restype for each DLL function."""
        lib = self._lib

        # Prefer lowercase names (RF IDeas sample style): these are the no-argument
        # forms.  The capitalized USBConnect/USBDisconnect variants may take a
        # long *pDevID pointer; calling them with argtypes=[] causes an access
        # violation as the DLL tries to dereference the missing pointer argument.
        self._usb_connect_name, self._usb_connect = self._pick_function_with_name(('usbConnect', 'USBConnect'))
        self._usb_disconnect = self._pick_function(('usbDisconnect', 'USBDisconnect'))
        self._get_active_id = self._pick_function(('getActiveID', 'GetActiveID'))
        self._set_dev_type_srch = self._pick_function(('SetDevTypeSrch',))
        self._set_connect_product = self._pick_function(('SetConnectProduct',))
        self._get_dev_cnt = self._pick_function(('GetDevCnt',))
        self._set_act_dev = self._pick_function(('SetActDev', 'SetActiveDev'))
        self._get_active_id32 = self._pick_function(('GetActiveID32', 'getActiveID32'))
        self._get_part_number_string = self._pick_function(('getPartNumberString', 'GetPartNumberString'))
        self._get_vid_pid_vendor_name = self._pick_function(('GetVidPidVendorName',))
        self._get_luid = self._pick_function(('GetLUID',))

        if self._usb_connect is None or self._usb_disconnect is None or self._get_active_id is None:
            raise PcProxError("Required pcProx API functions not found in DLL")

        self._usb_connect.argtypes = []
        self._usb_connect.restype = ctypes.c_short
        self._usb_disconnect.restype = ctypes.c_short
        self._get_active_id.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_ubyte,
        ]
        self._get_active_id.restype = ctypes.c_int
        if self._get_active_id32 is not None:
            self._get_active_id32.argtypes = [
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_short,
            ]
            self._get_active_id32.restype = ctypes.c_short

        if self._set_dev_type_srch is not None:
            self._set_dev_type_srch.restype = ctypes.c_short
        if self._set_connect_product is not None:
            self._set_connect_product.restype = ctypes.c_short
        if self._get_dev_cnt is not None:
            self._get_dev_cnt.restype = ctypes.c_short
        if self._set_act_dev is not None:
            self._set_act_dev.restype = ctypes.c_short
        if self._get_part_number_string is not None:
            self._get_part_number_string.restype = ctypes.POINTER(ctypes.c_char)
        if self._get_vid_pid_vendor_name is not None:
            self._get_vid_pid_vendor_name.restype = ctypes.POINTER(ctypes.c_char)
        if self._get_luid is not None:
            self._get_luid.restype = ctypes.c_ushort

    def _pick_function(self, names: tuple[str, ...]):
        for name in names:
            if hasattr(self._lib, name):
                return getattr(self._lib, name)
        return None

    def _pick_function_with_name(self, names: tuple[str, ...]):
        for name in names:
            if hasattr(self._lib, name):
                return name, getattr(self._lib, name)
        return "", None

    def _set_dev_type_search(self, device_type: int):
        if self._set_dev_type_srch is not None:
            try:
                self._set_dev_type_srch.restype = ctypes.c_short
                self._set_dev_type_srch.argtypes = [ctypes.c_short]
                self._set_dev_type_srch(ctypes.c_short(device_type))
            except TypeError:
                self._set_dev_type_srch.argtypes = [ctypes.c_ubyte]
                self._set_dev_type_srch(ctypes.c_ubyte(device_type))

    def _call_usb_connect(self) -> int:
        # RF IDeas sample uses no-argument usbConnect/USBConnect.
        # Keep this exact call shape for broadest compatibility.
        self._usb_connect.argtypes = []
        return int(self._usb_connect())

    def _call_get_active_id(self, buffer):
        return int(self._get_active_id(buffer, ctypes.c_ubyte(CARD_DATA_LEN)))

    def _read_part_number(self) -> str:
        if self._get_part_number_string is None:
            return ""
        try:
            ptr = self._get_part_number_string()
            return ctypes.string_at(ptr).decode('utf-8', errors='replace') if ptr else ""
        except Exception:
            return ""

    def _read_vid_pid_vendor_name(self) -> str:
        if self._get_vid_pid_vendor_name is None:
            return ""
        try:
            ptr = self._get_vid_pid_vendor_name()
            return ctypes.string_at(ptr).decode('utf-8', errors='replace') if ptr else ""
        except Exception:
            return ""

    def _read_luid(self) -> int:
        if self._get_luid is None:
            return 0
        try:
            return int(self._get_luid())
        except Exception:
            return 0

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    def __repr__(self):
        state = "connected" if self._connected else "disconnected"
        return f"<PcProxReader [{state}] dll={self._dll_path!r}>"
