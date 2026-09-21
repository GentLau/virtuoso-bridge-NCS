"""Best-effort child-process lifetime binding.

On Windows a supervised process's descendants (notably long-lived
``ssh -N -L`` tunnels) do not die when the parent is force-terminated.  A Job
Object with ``KILL_ON_JOB_CLOSE`` makes the OS tear down the whole tree when
the supervisor closes the job handle or exits.

On POSIX this is intentionally a no-op; the caller remains responsible for
explicit cleanup and must not claim a stronger guarantee than the platform
provides.
"""

from __future__ import annotations

import ctypes
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
_TH32CS_SNAPTHREAD = 0x00000004
_THREAD_SUSPEND_RESUME = 0x0002
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

if _IS_WINDOWS:
    from ctypes import wintypes

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JobObjectBasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_void_p),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JobObjectExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JobObjectBasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _ThreadEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", ctypes.c_long),
            ("tpDeltaPri", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
    ]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CreateToolhelp32Snapshot.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.Thread32First.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ThreadEntry32),
    ]
    _kernel32.Thread32First.restype = wintypes.BOOL
    _kernel32.Thread32Next.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ThreadEntry32),
    ]
    _kernel32.Thread32Next.restype = wintypes.BOOL
    _kernel32.OpenThread.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _kernel32.OpenThread.restype = wintypes.HANDLE
    _kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    _kernel32.ResumeThread.restype = wintypes.DWORD
else:
    _kernel32 = None


def _find_thread_id(pid: int) -> int | None:
    """Return one thread id owned by *pid* on Windows, if visible yet."""
    if not _IS_WINDOWS or _kernel32 is None:
        return None
    snapshot = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
    if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
        return None
    try:
        entry = _ThreadEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        ok = _kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while ok:
            if entry.th32OwnerProcessID == pid:
                return int(entry.th32ThreadID)
            ok = _kernel32.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snapshot)
    return None


class ProcessJob:
    """A Windows Job Object wrapper; a no-op on other platforms."""

    def __init__(self) -> None:
        self._handle: Any = None
        if not _IS_WINDOWS or _kernel32 is None:
            return
        handle = _kernel32.CreateJobObjectW(None, None)
        if not handle:
            logger.warning(
                "could not create Job Object: %s", ctypes.WinError(ctypes.get_last_error())
            )
            return
        info = _JobObjectExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _kernel32.SetInformationJobObject(
            handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            logger.warning(
                "could not configure Job Object: %s",
                ctypes.WinError(ctypes.get_last_error()),
            )
            _kernel32.CloseHandle(handle)
            return
        self._handle = handle

    def assign(self, proc: Any) -> bool:
        """Assign *proc* (and future descendants) to this job."""
        if self._handle is None or proc is None or proc.poll() is not None:
            return False
        try:
            handle = wintypes.HANDLE(int(proc._handle))
            ok = _kernel32.AssignProcessToJobObject(self._handle, handle)
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
        except Exception as exc:  # noqa: BLE001 - lifetime binding is best effort
            logger.warning(
                "could not assign process %s to Job Object: %s",
                getattr(proc, "pid", "?"),
                exc,
            )
            return False
        return True

    def resume(self, proc: Any, timeout: float = 2.0) -> bool:
        """Resume a process created with ``CREATE_SUSPENDED``.

        Call this only after :meth:`assign`.  Creating the process suspended
        and binding it before its first instruction makes descendant
        inheritance deterministic even when the supervisor itself is already
        running inside another Job Object.
        """
        if not _IS_WINDOWS or _kernel32 is None:
            return True
        if self._handle is None or proc is None or proc.poll() is not None:
            return False
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            thread_id = _find_thread_id(int(proc.pid))
            if thread_id is not None:
                thread = _kernel32.OpenThread(
                    _THREAD_SUSPEND_RESUME, False, thread_id
                )
                if thread:
                    try:
                        if _kernel32.ResumeThread(thread) != 0xFFFFFFFF:
                            return True
                    finally:
                        _kernel32.CloseHandle(thread)
            if time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        logger.warning(
            "could not resume process %s after Job Object assignment",
            getattr(proc, "pid", "?"),
        )
        return False

    def close(self) -> None:
        """Close the handle; ``KILL_ON_JOB_CLOSE`` tears down descendants."""
        if self._handle is None:
            return
        handle, self._handle = self._handle, None
        if not _kernel32.CloseHandle(handle):
            logger.warning(
                "could not close Job Object: %s",
                ctypes.WinError(ctypes.get_last_error()),
            )

__all__ = ["ProcessJob"]
