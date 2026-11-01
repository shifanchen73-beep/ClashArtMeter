"""Optional Windows-only TCP ownership lookup for Clash loopback proxy flows.

Reads the local Windows TCP table. Does not modify routing or inspect payloads.
A PID is attributed only if its executable is explicitly chrome.exe/msedge.exe.
If resolution is ambiguous, the caller must leave the traffic unattributed.
"""
from __future__ import annotations

import sys


def browser_ports() -> dict[int, str]:
    if sys.platform != 'win32':
        return {}
    try:
        return _windows_ports()
    except (OSError, ValueError, OverflowError):
        # Older Windows / unusual permissions must not stop data collection.
        return {}


def _windows_ports() -> dict[int, str]:
    import ctypes
    import socket
    from ctypes import wintypes

    class TcpRow(ctypes.Structure):
        _fields_ = [('state', wintypes.DWORD), ('local_addr', wintypes.DWORD),
                    ('local_port', wintypes.DWORD), ('remote_addr', wintypes.DWORD),
                    ('remote_port', wintypes.DWORD), ('pid', wintypes.DWORD)]

    iphelper = ctypes.WinDLL('iphlpapi', use_last_error=True)
    get_table = iphelper.GetExtendedTcpTable
    get_table.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                          wintypes.BOOL, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG]
    get_table.restype = wintypes.DWORD
    size = wintypes.DWORD(0)
    # AF_INET = 2, TCP_TABLE_OWNER_PID_ALL = 5, ERROR_INSUFFICIENT_BUFFER = 122.
    result = get_table(None, ctypes.byref(size), False, socket.AF_INET, 5, 0)
    if result not in (0, 122) or not (4 <= size.value <= 8_000_000):
        return {}
    buffer = ctypes.create_string_buffer(size.value)
    if get_table(buffer, ctypes.byref(size), False, socket.AF_INET, 5, 0) != 0:
        return {}
    count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
    if count > (len(buffer) - 4) // ctypes.sizeof(TcpRow):
        return {}
    rows = ctypes.cast(ctypes.byref(buffer, 4), ctypes.POINTER(TcpRow * count)).contents

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    open_process = kernel.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    get_name = kernel.QueryFullProcessImageNameW
    get_name.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                         ctypes.POINTER(wintypes.DWORD)]
    get_name.restype = wintypes.BOOL
    close_handle = kernel.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    names: dict[int, str] = {}

    def process_name(pid: int) -> str:
        if pid in names:
            return names[pid]
        result = ''
        handle = open_process(0x1000, False, pid) if pid else None
        if handle:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                length = wintypes.DWORD(len(buf))
                if get_name(handle, 0, buf, ctypes.byref(length)):
                    executable = buf.value.replace('/', '\\').rsplit('\\', 1)[-1].lower()
                    result = {'chrome.exe': 'chrome', 'msedge.exe': 'edge'}.get(executable, '')
            finally:
                close_handle(handle)
        names[pid] = result
        return result

    by_port: dict[int, set[str]] = {}
    for row in rows:
        if row.state != 5:  # TCP ESTABLISHED
            continue
        port = socket.ntohs(row.local_port & 0xFFFF)
        name = process_name(int(row.pid))
        if name:
            by_port.setdefault(port, set()).add(name)
    return {port: next(iter(names)) for port, names in by_port.items() if len(names) == 1}
