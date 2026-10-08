"""Middle-layer Skill port (TCP client to the bottom daemon).

Request: {"skill", "timeout", "token", "log_level", "log_max_bytes"}
Response: 02/15 + JSON {"value"|"error", "log"} + 1e

This is the only wire format: anything else is treated as an error.
"""

from __future__ import annotations

import json
import logging
import socket
import time

from pyapi.models import ExecutionStatus, VirtuosoResult

logger = logging.getLogger(__name__)

STX = "\x02"
NAK = "\x15"
RS = "\x1e"
_RECV_BUF_SIZE = 1024 * 1024
_CONNECT_RETRY_DELAY = 0.2
_CONNECT_GRACE_SECONDS = 3.0
_MAX_ATTEMPTS = 3  # spec §5.8: at most 3 transport attempts, pre-side-effect only


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0.0:
        raise socket.timeout
    return remaining


class _DeliveredRequestFailure(Exception):
    """The request had already been written when the connection failed.

    Such a failure must never trigger a resend: the daemon may have executed
    the SKILL (spec §5.8 / 并发设计 §1: 已投递后不得重试).
    """

    def __init__(self, cause: BaseException) -> None:
        super().__init__(str(cause))
        self.cause = cause


class SkillClient:
    """Pure TCP Skill port; transport details are injected by the middle."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 65432,
        timeout: float = 30.0,
        token: str | None = None,
        log_level: str = "all",
        log_max_bytes: int = 65536,
        connect_timeout: float | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.token = token
        self.log_level = log_level
        self.log_max_bytes = log_max_bytes
        #: sub-budget for TCP connect (spec §5.8: runtime.connect_timeout)
        self.connect_timeout = connect_timeout

    def execute_skill(
        self,
        skill_code: str,
        timeout: float | None = None,
        *,
        log_level: str | None = None,
        log_max_bytes: int | None = None,
    ) -> VirtuosoResult:
        return self.execute_skill_checked(
            skill_code,
            timeout,
            log_level=log_level,
            log_max_bytes=log_max_bytes,
        )[0]

    def execute_skill_checked(
        self,
        skill_code: str,
        timeout: float | None = None,
        *,
        log_level: str | None = None,
        log_max_bytes: int | None = None,
    ) -> tuple[VirtuosoResult, str]:
        """Return the public result plus an internal delivery classification."""
        effective = timeout if timeout is not None else self.timeout
        deadline = time.monotonic() + effective
        start = time.monotonic()
        attempts = 0
        while True:
            if time.monotonic() >= deadline:
                return (
                    VirtuosoResult(
                        status=ExecutionStatus.ERROR,
                        errors=["SKILL execution timed out"],
                        execution_time=time.monotonic() - start,
                    ),
                    "not_delivered",
                )
            attempts += 1
            try:
                raw = self._execute_once(
                    skill_code,
                    effective,
                    deadline,
                    log_level=log_level,
                    log_max_bytes=log_max_bytes,
                )
                elapsed = time.monotonic() - start
                if not raw or raw[0] not in (STX, NAK):
                    return self._parse_response(raw, elapsed), "delivered_unknown"
                status = self._response_status(raw)
                if status == "busy":
                    # daemon 读到请求后直接 NAK busy、未触碰 Virtuoso：
                    # 本次请求确定未执行，可安全重试（不标记结果未知）。
                    return self._parse_response(raw, elapsed), "not_delivered"
                if status == "timeout":
                    return self._parse_response(raw, elapsed), "delivered_unknown"
                return self._parse_response(raw, elapsed), "completed"
            except _DeliveredRequestFailure:
                # the request may already have run: report the frozen
                # "result unknown" wording and never resend
                return (
                    VirtuosoResult(
                        status=ExecutionStatus.ERROR,
                        errors=["SKILL execution timed out"],
                        execution_time=time.monotonic() - start,
                    ),
                    "delivered_unknown",
                )
            except (ConnectionRefusedError, ConnectionResetError):
                # nothing was sent (connect-phase failure): safe to retry, but
                # at most _MAX_ATTEMPTS attempts in total
                if (
                    attempts >= _MAX_ATTEMPTS
                    or time.monotonic() >= start + _CONNECT_GRACE_SECONDS
                ):
                    return (
                        VirtuosoResult(
                            status=ExecutionStatus.ERROR,
                            errors=["Daemon connection failed (refused/reset)"],
                            execution_time=time.monotonic() - start,
                        ),
                        "not_delivered",
                    )
                time.sleep(min(_CONNECT_RETRY_DELAY, deadline - time.monotonic()))
            except socket.timeout:
                # socket.timeout is an OSError subclass; catch it first
                return (
                    VirtuosoResult(
                        status=ExecutionStatus.ERROR,
                        errors=["SKILL execution timed out"],
                        execution_time=time.monotonic() - start,
                    ),
                    "not_delivered",
                )
            except OSError as exc:
                return (
                    VirtuosoResult(
                        status=ExecutionStatus.ERROR,
                        errors=[f"Daemon connection failed: {exc}"],
                        execution_time=time.monotonic() - start,
                    ),
                    "not_delivered",
                )

    def probe(self, timeout: float | None = None) -> str:
        """Side-effect-free daemon readiness probe."""
        effective = timeout if timeout is not None else self.timeout
        deadline = time.monotonic() + effective
        try:
            raw = self._round_trip(
                {"probe": True, "token": self.token},
                effective,
                deadline,
            )
        except Exception:  # noqa: BLE001 - timeout/busy maps to unknown
            return "unknown"
        if not raw or raw[0] not in (STX, NAK):
            return "unknown"
        status = self._response_status(raw)
        return status if status in ("idle", "busy") else "unknown"

    def _round_trip(
        self,
        payload: dict,
        timeout: float,
        deadline: float,
    ) -> str:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            connect_budget = _remaining_timeout(deadline)
            if self.connect_timeout is not None:
                connect_budget = min(
                    connect_budget, max(self.connect_timeout, 0.0),
                ) or 0.0
            s.settimeout(connect_budget)
            s.connect((self.host, self.port))
            request_timeout = min(timeout, _remaining_timeout(deadline))
            payload = dict(payload)
            payload["timeout"] = request_timeout
            send_timeout = _remaining_timeout(deadline)
            payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            try:
                s.settimeout(send_timeout)
                s.sendall(payload_bytes)
                s.shutdown(socket.SHUT_WR)
                chunks: list[bytes] = []
                while True:
                    s.settimeout(_remaining_timeout(deadline))
                    chunk = s.recv(_RECV_BUF_SIZE)
                    if not chunk:
                        break
                    chunks.append(chunk)
            except OSError as exc:  # includes socket.timeout
                # anything from here on may have reached the daemon
                raise _DeliveredRequestFailure(exc) from exc
            return b"".join(chunks).decode("utf-8", errors="ignore")

    def _execute_once(
        self,
        skill_code: str,
        timeout: float,
        deadline: float,
        *,
        log_level: str | None = None,
        log_max_bytes: int | None = None,
    ) -> str:
        return self._round_trip(
            {
                "skill": skill_code,
                "token": self.token,
                "log_level": (
                    log_level if log_level is not None else self.log_level
                ),
                "log_max_bytes": (
                    log_max_bytes
                    if log_max_bytes is not None
                    else self.log_max_bytes
                ),
            },
            timeout,
            deadline,
        )

    @staticmethod
    def _response_status(raw: str) -> str | None:
        if not raw or raw[0] not in (STX, NAK):
            return None
        try:
            data = json.loads(raw[1:].rstrip(RS))
        except (json.JSONDecodeError, ValueError):
            return None
        status = data.get("status")
        return status if isinstance(status, str) else None

    @staticmethod
    def _parse_response(raw: str, elapsed: float) -> VirtuosoResult:
        if not raw:
            return VirtuosoResult(status=ExecutionStatus.ERROR,
                                  errors=["SKILL execution timed out"],
                                  warnings=["daemon returned an empty response"],
                                  execution_time=elapsed)
        if not (raw.startswith(STX) or raw.startswith(NAK)):
            return VirtuosoResult(
                status=ExecutionStatus.ERROR,
                errors=["Response did not contain a standard status marker"],
                execution_time=elapsed,
            )
        status_mark = raw[0]
        body = raw[1:].rstrip(RS)
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return VirtuosoResult(
                status=ExecutionStatus.ERROR,
                errors=["Malformed response: payload is not JSON"],
                execution_time=elapsed,
            )

        log = data.get("log", "") or ""
        warnings = data.get("warnings") or []
        if status_mark == STX:
            return VirtuosoResult(
                status=ExecutionStatus.SUCCESS,
                output=data.get("value", ""),
                log=log,
                warnings=list(warnings),
                execution_time=elapsed,
            )
        return VirtuosoResult(
            status=ExecutionStatus.ERROR,
            errors=[data.get("error", "")],
            log=log,
            warnings=list(warnings),
            execution_time=elapsed,
        )


__all__ = ["SkillClient"]
