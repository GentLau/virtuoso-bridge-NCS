"""Best-effort child-process lifetime binding.

On Windows a supervised process's descendants (notably long-lived
``ssh -N -L`` tunnels) do not die when the parent is force-terminated.  A Job
Object with ``KILL_ON_JOB_CLOSE`` makes the OS tear down the whole tree when
the supervisor closes the job handle or exits.

On POSIX this is intentionally a no-op: the platform's process/session rules
already cover the supported deployments, and the caller still gets the normal
explicit ``terminate()`` path.
"""

from __future__ import annotations

import ctypes
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9

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
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
else:
    _kernel32 = None


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
            logger.warning("could not assign process %s to Job Object: %s", getattr(proc, "pid", "?"), exc)
            return False
        return True

    def terminate(self) -> None:
        """Terminate every process currently assigned to the job."""
        if self._handle is None:
            return
        if not _kernel32.TerminateJobObject(self._handle, 1):
            logger.warning(
                "could not terminate Job Object: %s",
                ctypes.WinError(ctypes.get_last_error()),
            )

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

    def __enter__(self) -> "ProcessJob":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = ["ProcessJob"]
