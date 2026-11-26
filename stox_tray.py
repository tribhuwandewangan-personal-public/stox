"""
Stox Production Workstation — Windows System Tray Supervisor.

Runs dashboard_server.py in production mode (AUTO_SCHEDULE=1, CATALYST_AUTO_SCAN=1),
monitors Valkey availability with native Windows system-level balloon alerts when
Valkey is offline, and provides a Taskbar / System Tray icon with quick actions.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import webbrowser
import zlib

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(PROJECT_ROOT, "storage", "stox.ico")
LOG_PATH = os.path.join(PROJECT_ROOT, "storage", "stox_production.log")
DASHBOARD_URL = "http://127.0.0.1:8765"

VALKEY_HOST = os.getenv("VALKEY_HOST", "localhost")
VALKEY_PORT = int(os.getenv("VALKEY_PORT", "6379"))


def ensure_stox_icon(path: str = ICON_PATH) -> str:
    """Generates a 32x32 RGBA .ico file in pure Python (no Pillow required)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        return path

    w, h = 32, 32
    rows = []
    for y in range(h):
        row = bytearray([0])  # PNG filter type 0
        for x in range(w):
            # Rounded dark navy badge with cyan/emerald upward trend bar
            dx, dy = abs(x - 15.5), abs(y - 15.5)
            in_badge = (dx <= 14 and dy <= 14) and not (dx > 11 and dy > 11)
            if not in_badge:
                row.extend((0, 0, 0, 0))
                continue
            # Rising chart line + bars
            is_bar1 = (7 <= x <= 10) and (17 <= y <= 24)
            is_bar2 = (13 <= x <= 16) and (13 <= y <= 24)
            is_bar3 = (19 <= x <= 22) and (8 <= y <= 24)
            if is_bar3:
                row.extend((16, 185, 129, 255))  # Emerald
            elif is_bar1 or is_bar2:
                row.extend((56, 189, 248, 255))  # Sky cyan
            else:
                row.extend((15, 23, 42, 255))    # Slate-900
        rows.append(bytes(row))

    raw_img = b"".join(rows)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw_img, 9)) + _chunk(b"IEND", b"")
    ico_header = struct.pack("<HHH", 0, 1, 1)
    ico_entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png), 6 + 16)
    with open(path, "wb") as f:
        f.write(ico_header + ico_entry + png)
    return path


def is_valkey_available(host: str = VALKEY_HOST, port: int = VALKEY_PORT, timeout: float = 1.5) -> bool:
    """Probes Valkey TCP + PING cleanly."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(b"*1\r\n$4\r\nPING\r\n")
            data = sock.recv(64)
            return b"PONG" in data
    except Exception:
        return False


# ---- Win32 System Tray Constants & Structs ----
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
TPM_BOTTOMALIGN = 0x0020
TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002

ID_OPEN = 1001
ID_SCAN = 1002
ID_VALKEY = 1003
ID_RESTART = 1004
ID_EXIT = 1005

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


class StoxTraySupervisor:
    def __init__(self):
        self.icon_path = ensure_stox_icon()
        self.proc: subprocess.Popen | None = None
        self.stop_event = threading.Event()
        self.hwnd = None
        self.hicon = None
        self._last_valkey_state: bool | None = None

        self.user32 = ctypes.windll.user32
        self.shell32 = ctypes.windll.shell32
        self.kernel32 = ctypes.windll.kernel32
        self._mutex = None
        self._configure_win32_types()

    def _configure_win32_types(self) -> None:
        """Set explicit 64-bit-safe argtypes/restype on Win32 API calls."""
        LRESULT = getattr(wintypes, "LPARAM", ctypes.c_ssize_t)
        UINT_PTR = getattr(wintypes, "WPARAM", ctypes.c_size_t)

        self.kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self.kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        self.kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel32.CreateMutexW.restype = wintypes.HANDLE
        self.kernel32.GetLastError.argtypes = []
        self.kernel32.GetLastError.restype = wintypes.DWORD

        self.user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        self.user32.RegisterClassW.restype = wintypes.ATOM
        self.user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        ]
        self.user32.CreateWindowExW.restype = wintypes.HWND
        self.user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.DefWindowProcW.restype = LRESULT
        self.user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        self.user32.LoadImageW.restype = wintypes.HANDLE
        self.user32.CreatePopupMenu.argtypes = []
        self.user32.CreatePopupMenu.restype = wintypes.HMENU
        self.user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, UINT_PTR, wintypes.LPCWSTR]
        self.user32.AppendMenuW.restype = wintypes.BOOL
        self.user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.user32.GetCursorPos.restype = wintypes.BOOL
        self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user32.SetForegroundWindow.restype = wintypes.BOOL
        self.user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, wintypes.HWND, wintypes.LPVOID,
        ]
        self.user32.TrackPopupMenu.restype = wintypes.BOOL
        self.user32.DestroyMenu.argtypes = [wintypes.HMENU]
        self.user32.DestroyMenu.restype = wintypes.BOOL
        self.user32.DestroyWindow.argtypes = [wintypes.HWND]
        self.user32.DestroyWindow.restype = wintypes.BOOL
        self.user32.PostQuitMessage.argtypes = [ctypes.c_int]
        self.user32.PostQuitMessage.restype = None
        self.user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self.user32.GetMessageW.restype = wintypes.BOOL
        self.user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        self.user32.TranslateMessage.restype = wintypes.BOOL
        self.user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        self.user32.DispatchMessageW.restype = LRESULT
        self.shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        self.shell32.Shell_NotifyIconW.restype = wintypes.BOOL

    def _acquire_single_instance(self) -> bool:
        """Ensure only one StoxTraySupervisor runs at a time using a Win32 named mutex."""
        ERROR_ALREADY_EXISTS = 183
        self._mutex = self.kernel32.CreateMutexW(None, False, "Local\\StoxWorkstationTrayMutex")
        if self.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return False
        return True

    def _start_backend(self) -> None:
        if self.proc and self.proc.poll() is None:
            return
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        env = os.environ.copy()
        env["AUTO_SCHEDULE"] = "1"
        env["CATALYST_AUTO_SCAN"] = "1"
        env["PYTHONUNBUFFERED"] = "1"

        py_exe = sys.executable
        if py_exe.lower().endswith("pythonw.exe"):
            cand = py_exe[:-len("pythonw.exe")] + "python.exe"
            if os.path.exists(cand):
                py_exe = cand

        log_f = open(LOG_PATH, "a", encoding="utf-8")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        self.proc = subprocess.Popen(
            [py_exe, os.path.join(PROJECT_ROOT, "dashboard_server.py"), "--no-browser"],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    def _stop_backend(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None

    def show_balloon(self, title: str, msg: str, warning: bool = False) -> None:
        if not self.hwnd:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_INFO
        nid.szInfoTitle = title[:63]
        nid.szInfo = msg[:255]
        nid.dwInfoFlags = NIIF_WARNING if warning else NIIF_INFO
        self.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _monitor_loop(self) -> None:
        # Short initial delay so tray icon registers before first balloon
        time.sleep(1.5)
        while not self.stop_event.is_set():
            # 1. Keep backend alive
            if self.proc is None or self.proc.poll() is not None:
                self._start_backend()

            # 2. Check Valkey health and fire system-level alert if unavailable
            valkey_ok = is_valkey_available()
            if self._last_valkey_state is None:
                if not valkey_ok:
                    self.show_balloon(
                        "Stox Alert: Valkey Offline",
                        f"Valkey is not reachable on {VALKEY_HOST}:{VALKEY_PORT}. Running in SQLite fallback mode.",
                        warning=True,
                    )
            elif self._last_valkey_state and not valkey_ok:
                self.show_balloon(
                    "Stox Alert: Valkey Disconnected",
                    f"Lost connection to Valkey ({VALKEY_HOST}:{VALKEY_PORT}). Switched to SQLite fallback.",
                    warning=True,
                )
            elif not self._last_valkey_state and valkey_ok:
                self.show_balloon(
                    "Stox: Valkey Connected",
                    f"Valkey is online at {VALKEY_HOST}:{VALKEY_PORT}.",
                    warning=False,
                )
            self._last_valkey_state = valkey_ok

            self.stop_event.wait(60)

    def _trigger_catalyst_scan(self) -> None:
        def _run():
            try:
                import requests
                r = requests.post(
                    f"{DASHBOARD_URL}/api/catalysts/scan",
                    headers={"X-Stox-Request": "1", "Content-Type": "application/json"},
                    json={},
                    timeout=30,
                )
                if r.status_code == 200:
                    d = r.json()
                    self.show_balloon(
                        "Stox Catalyst Scan Complete",
                        f"Saved {d.get('saved_catalysts', 0)} catalysts ({d.get('tier_a_count', 0)} Tier A).",
                    )
                else:
                    self.show_balloon("Stox Catalyst Scan", f"Server returned HTTP {r.status_code}", warning=True)
            except Exception as e:
                self.show_balloon("Stox Catalyst Scan Failed", str(e)[:200], warning=True)

        threading.Thread(target=_run, daemon=True).start()

    def _show_context_menu(self) -> None:
        hmenu = self.user32.CreatePopupMenu()
        self.user32.AppendMenuW(hmenu, 0, ID_OPEN, "Open Stox Dashboard")
        self.user32.AppendMenuW(hmenu, 0, ID_SCAN, "Run Catalyst Scan Now")
        self.user32.AppendMenuW(hmenu, 0, ID_VALKEY, "Check Valkey Status")
        self.user32.AppendMenuW(hmenu, 0, ID_RESTART, "Restart Backend Server")
        self.user32.AppendMenuW(hmenu, 0x0800, 0, None)  # Separator
        self.user32.AppendMenuW(hmenu, 0, ID_EXIT, "Exit Stox")

        pt = wintypes.POINT()
        self.user32.GetCursorPos(ctypes.byref(pt))
        self.user32.SetForegroundWindow(self.hwnd)
        self.user32.TrackPopupMenu(hmenu, TPM_LEFTALIGN | TPM_BOTTOMALIGN | TPM_RIGHTBUTTON, pt.x, pt.y, 0, self.hwnd, None)
        self.user32.DestroyMenu(hmenu)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == WM_LBUTTONDBLCLK:
                webbrowser.open(DASHBOARD_URL)
            elif lparam == WM_RBUTTONUP:
                self._show_context_menu()
            return 0
        elif msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            if cmd == ID_OPEN:
                webbrowser.open(DASHBOARD_URL)
            elif cmd == ID_SCAN:
                self._trigger_catalyst_scan()
            elif cmd == ID_VALKEY:
                ok = is_valkey_available()
                self.show_balloon(
                    "Stox Valkey Status",
                    f"Valkey is ONLINE at {VALKEY_HOST}:{VALKEY_PORT}." if ok else f"Valkey is OFFLINE at {VALKEY_HOST}:{VALKEY_PORT} (using SQLite fallback).",
                    warning=not ok,
                )
            elif cmd == ID_RESTART:
                self._stop_backend()
                self._start_backend()
                self.show_balloon("Stox Server", "Backend server restarted.")
            elif cmd == ID_EXIT:
                self.stop_event.set()
                self._stop_backend()
                self.user32.DestroyWindow(hwnd)
            return 0
        elif msg == WM_DESTROY:
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = hwnd
            nid.uID = 1
            self.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            self.user32.PostQuitMessage(0)
            return 0
        return self.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self) -> None:
        if not self._acquire_single_instance():
            # Already running — just open the dashboard instead of adding a duplicate tray icon
            webbrowser.open(DASHBOARD_URL)
            return

        hinst = self.kernel32.GetModuleHandleW(None)
        wndproc_cb = WNDPROC(self._wnd_proc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = wndproc_cb
        wc.hInstance = hinst
        wc.lpszClassName = "StoxWorkstationTrayClass"
        self.user32.RegisterClassW(ctypes.byref(wc))

        self.hwnd = self.user32.CreateWindowExW(
            0, wc.lpszClassName, "Stox Workstation", 0, 0, 0, 0, 0, None, None, hinst, None
        )
        self.hicon = self.user32.LoadImageW(None, self.icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self.hicon
        nid.szTip = "Stox Workstation (Auto-Analysis + Catalyst Radar)"
        self.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

        self._start_backend()
        threading.Thread(target=self._monitor_loop, daemon=True).start()

        msg = wintypes.MSG()
        while self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            self.user32.TranslateMessage(ctypes.byref(msg))
            self.user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    if "--make-icon" in sys.argv:
        print(ensure_stox_icon())
    else:
        StoxTraySupervisor().run()
