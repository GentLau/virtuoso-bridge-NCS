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


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0.0:
        raise socket.timeout
    return remaining


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
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.token = token
        self.log_level = log_level
        self.log_max_bytes = log_max_bytes

    def execute_skill(self, skill_code: str, timeout: float | None = None) -> VirtuosoResult:
        effective = timeout if timeout is not None else self.timeout
        deadline = time.monotonic() + effective
        start = time.monotonic()
        while True:
            if time.monotonic() >= deadline:
                return VirtuosoResult(
                    status=ExecutionStatus.ERROR,
                    errors=["SKILL execution timed out"],
                    execution_time=time.monotonic() - start,
                )
            try:
                raw = self._execute_once(skill_code, effective, deadline)
                elapsed = time.monotonic() - start
                return self._parse_response(raw, elapsed)
            except ConnectionRefusedError:
                if time.monotonic() >= start + _CONNECT_GRACE_SECONDS:
                    return VirtuosoResult(
                        status=ExecutionStatus.ERROR,
                        errors=["Connection refused by daemon"],
                        execution_time=time.monotonic() - start,
                    )
                time.sleep(min(_CONNECT_RETRY_DELAY, deadline - time.monotonic()))
            except socket.timeout:
                # socket.timeout is an OSError subclass; catch it first
                return VirtuosoResult(
                    status=ExecutionStatus.ERROR,
                    errors=["SKILL execution timed out"],
                    execution_time=time.monotonic() - start,
                )
            except OSError as exc:
                return VirtuosoResult(
                    status=ExecutionStatus.ERROR,
                    errors=[f"Socket error: {exc}"],
                    execution_time=time.monotonic() - start,
                )

    def _execute_once(self, skill_code: str, timeout: float, deadline: float) -> str:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(_remaining_timeout(deadline))
            s.connect((self.host, self.port))
            request_timeout = min(timeout, _remaining_timeout(deadline))
            payload = {
                "skill": skill_code,
                "timeout": request_timeout,
                "token": self.token,
                "log_level": self.log_level,
                "log_max_bytes": self.log_max_bytes,
            }
            s.settimeout(_remaining_timeout(deadline))
            s.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            s.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                s.settimeout(_remaining_timeout(deadline))
                chunk = s.recv(_RECV_BUF_SIZE)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", errors="ignore")

    @staticmethod
    def _parse_response(raw: str, elapsed: float) -> VirtuosoResult:
        if not raw:
            return VirtuosoResult(status=ExecutionStatus.ERROR, errors=["Empty response from daemon"], execution_time=elapsed)
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
        if status_mark == STX:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=data.get("value", ""), log=log, execution_time=elapsed)
        return VirtuosoResult(status=ExecutionStatus.ERROR, errors=[data.get("error", "")], log=log, execution_time=elapsed)


__all__ = ["SkillClient"]
