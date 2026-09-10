# -*- coding: utf-8 -*-
"""CDS.log 增量返回的独立最小验证单元。

这个文件只验证 daemon 侧最关键的算法，不连接 Virtuoso，也不依赖仓库现有
代码：

* 用 byte cursor 读取 ``[cursor, end_offset)``；
* 用 ``VB-BEGIN``/``VB-END`` 模拟底层 marker；
* 按 ``all/warn/error/off`` 过滤 ``\\e``/``\\w`` 前缀；
* 超过 ``log_max_bytes`` 时降级为 error-only，并带截断说明；
* 文件被轮转/清空后自动把 cursor 重置为 0。

``SkillLogEmitter`` 模拟只能被 CIW 调用的底层写日志动作，
``CdsLogIncrementReader`` 模拟与 CDS.log 同机的 daemon 读增量动作。
"""
from __future__ import annotations

import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


_VALID_LEVELS = {"off", "all", "warn", "error"}


@dataclass(frozen=True)
class SkillResult:
    """模拟上层看到的 VirtuosoResult 子集；重点是新增 ``log`` 字段。"""

    status: str
    output: str
    log: str = ""

    def to_dict(self) -> dict:
        return {"status": self.status, "output": self.output, "log": self.log}


@dataclass(frozen=True)
class LogIncrement:
    """一次 Skill 调用对应的裁剪后日志。"""

    text: str
    start_offset: int
    end_offset: int
    truncated: bool = False
    level: str = "all"

    @property
    def byte_length(self) -> int:
        return len(self.text.encode("utf-8"))


class CdsLogIncrementReader:
    """持有一个 log_path + byte cursor 的 daemon 侧 reader。"""

    def __init__(
        self,
        path: Path,
        *,
        log_level: str = "all",
        log_max_bytes: int = 64 * 1024,
        start_at_end: bool = True,
    ) -> None:
        if log_level not in _VALID_LEVELS:
            raise ValueError("log_level must be off/all/warn/error")
        if log_max_bytes < 1:
            raise ValueError("log_max_bytes must be >= 1")
        self.path = Path(path)
        self.log_level = log_level
        self.log_max_bytes = log_max_bytes
        self._lock = threading.RLock()
        self._cursor = self.path.stat().st_size if start_at_end and self.path.exists() else 0

    @property
    def cursor(self) -> int:
        with self._lock:
            return self._cursor

    def read_increment(self, end_offset: Optional[int] = None) -> LogIncrement:
        """读取当前 cursor 到 end_offset 的字节，并推进 cursor。

        文件长度比 cursor 短时视为轮转/清空，先把起点重置为 0；这个判断在
        读文件之前完成，因此不会把旧 offset 当成 EOF 静默吞掉新日志。
        """

        with self._lock:
            if self.path.exists():
                file_size = self.path.stat().st_size
            else:
                file_size = 0
            if file_size < self._cursor:
                self._cursor = 0
            start = self._cursor
            end = file_size if end_offset is None else min(max(end_offset, 0), file_size)
            if end < start:
                # 调用方传入了比 cursor 更早的 offset；按当前文件尾读取空增量，
                # 不倒退 cursor，避免重复消费已经读过的字节。
                end = start
            if end > start:
                with self.path.open("rb") as stream:
                    stream.seek(start)
                    raw = stream.read(end - start)
            else:
                raw = b""
            self._cursor = end
            text = raw.decode("utf-8", errors="replace")
            filtered, truncated = self._filter_and_bound(text)
            return LogIncrement(
                text=filtered,
                start_offset=start,
                end_offset=end,
                truncated=truncated,
                level=self.log_level,
            )

    def _filter_and_bound(self, text: str) -> Tuple[str, bool]:
        if self.log_level == "off":
            # off 仍然消费 cursor，只是不把日志放进响应。
            return "", False

        selected: List[Tuple[str, str]] = []
        for line in text.splitlines(keepends=True):
            level = _line_level(line)
            if _is_marker(line) or _level_allowed(level, self.log_level):
                selected.append((line, level))

        full_text = "".join(line for line, _level in selected)
        if _byte_len(full_text) <= self.log_max_bytes:
            return full_text, False

        # 第一降级：保留 marker 和 error 行。marker 是人读边界，即使配置为
        # all 且超长，也不把它们当普通 info 丢掉。
        error_only = [
            (line, level)
            for line, level in selected
            if level == "error" or _is_marker(line)
        ]
        error_text = "".join(line for line, _level in error_only)
        dropped = max(0, _byte_len(full_text) - _byte_len(error_text))
        notice = "... [log truncated: error-only, {} bytes dropped]\n".format(dropped)
        candidate = error_text + notice
        if _byte_len(candidate) <= self.log_max_bytes:
            return candidate, True

        # 第二降级：error 行仍然太多时，只保留头尾（设计标准给出的 100
        # 行上限）。budget 很小时再按字节预算安全裁剪，保证返回值不超长。
        error_lines = [line for line, level in error_only if level == "error"]
        markers = [line for line, _level in error_only if _is_marker(line)]
        compact = _head_tail_with_markers(error_lines, markers, 100)
        compact_text = _fit_text_with_notice(compact, notice, self.log_max_bytes)
        return compact_text, True


class SkillLogEmitter:
    """模拟底层 marker + flush + end_offset 返回。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._lock = threading.Lock()

    def invoke(self, lines: Iterable[str], reader: CdsLogIncrementReader) -> LogIncrement:
        """写一段本次 Skill 的日志，然后让 daemon 读取对应增量。"""

        with self._lock:
            self._append_line("VB-BEGIN")
            for line in lines:
                self._append_line(line)
            self._append_line("VB-END")
            # hiFlushLogFile 的最小等价物：flush + fsync，随后 fileLength 就
            # 是可交给 daemon 的 end_offset。
            with self.path.open("ab") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            end_offset = self.path.stat().st_size
            return reader.read_increment(end_offset)

    def _append_line(self, line: str) -> None:
        normalized = line if line.endswith("\n") else line + "\n"
        with self.path.open("ab") as stream:
            stream.write(normalized.encode("utf-8"))
            stream.flush()



class DemoSkillExecutor:
    """把一次伪 Skill 调用包装成 ``{value, log}`` 返回值。"""

    def __init__(self, path: Path, reader: CdsLogIncrementReader) -> None:
        self.emitter = SkillLogEmitter(path)
        self.reader = reader

    def execute_skill(self, skill_code: str, log_lines: Iterable[str]) -> SkillResult:
        increment = self.emitter.invoke(log_lines, self.reader)
        # skill_code 只作为 demo 的调用标签；这里不求值。
        return SkillResult(status="success", output=skill_code, log=increment.text)


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _is_marker(line: str) -> bool:
    return "VB-BEGIN" in line or "VB-END" in line


def _line_level(line: str) -> str:
    if line.startswith("\\e"):
        return "error"
    if line.startswith("\\w"):
        return "warning"
    # \o/\i/\p/无前缀都按 info，不丢无法解析的行。
    return "info"


def _level_allowed(level: str, configured: str) -> bool:
    if configured == "all":
        return True
    if configured == "warn":
        return level in {"warning", "error"}
    if configured == "error":
        return level == "error"
    return False


def _head_tail_with_markers(
    error_lines: Sequence[str],
    markers: Sequence[str],
    per_side: int,
) -> List[str]:
    if len(error_lines) <= per_side * 2:
        chosen = list(error_lines)
    else:
        chosen = list(error_lines[:per_side]) + list(error_lines[-per_side:])
    # 让 marker 尽量位于输出边界；去重后保持自然顺序。
    result: List[str] = []
    for line in list(markers[:1]) + chosen + list(markers[-1:]):
        if line not in result:
            result.append(line)
    return result


def _fit_text_with_notice(
    lines: Sequence[str],
    notice: str,
    max_bytes: int,
) -> str:
    """在 max_bytes 内保留尽可能多的完整行和截断说明。"""

    # notice 是 ASCII，极小 max_bytes 时也要返回一个合法的 UTF-8 前缀。
    notice_bytes = notice.encode("utf-8")
    if len(notice_bytes) >= max_bytes:
        return notice_bytes[:max_bytes].decode("utf-8", errors="ignore")

    budget = max_bytes - len(notice_bytes)
    # 先从头尾交替取行，体现 head/tail 策略；最后按原顺序拼回。
    selected_indexes: List[int] = []
    left, right = 0, len(lines) - 1
    used = 0
    take_left = True
    while left <= right:
        index = left if take_left else right
        line_bytes = _byte_len(lines[index])
        if used + line_bytes <= budget:
            selected_indexes.append(index)
            used += line_bytes
            if take_left:
                left += 1
            else:
                right -= 1
        else:
            # 当前一端放不下时，尝试另一端；两端都放不下就结束。
            if take_left:
                alternate = right
                alternate_bytes = _byte_len(lines[alternate]) if alternate >= left else 0
                if alternate >= left and used + alternate_bytes <= budget:
                    selected_indexes.append(alternate)
                    used += alternate_bytes
                    right -= 1
                else:
                    break
            else:
                alternate = left
                alternate_bytes = _byte_len(lines[alternate]) if alternate <= right else 0
                if alternate <= right and used + alternate_bytes <= budget:
                    selected_indexes.append(alternate)
                    used += alternate_bytes
                    left += 1
                else:
                    break
        take_left = not take_left

    selected_indexes.sort()
    text = "".join(lines[index] for index in selected_indexes) + notice
    # 理论上不会超出；对极端行长做最后一道 UTF-8 安全保护。
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def run_demo() -> dict:
    """运行两次调用、过滤和轮转示例。"""

    with tempfile.TemporaryDirectory(prefix="vb-cdslog-demo-") as temporary:
        path = Path(temporary) / "CDS.log"
        reader = CdsLogIncrementReader(path, log_level="all", log_max_bytes=4096)
        executor = DemoSkillExecutor(path, reader)
        first = executor.execute_skill(
            "1+1", ["\\i first info", "\\w first warning"]
        )
        second = executor.execute_skill(
            "2+2", ["\\e second error", "second info"]
        )
        summary = {
            "first_result": first.to_dict(),
            "second_result": second.to_dict(),
            "cursor": reader.cursor,
            "second_only_contains_error": "second error" in second.log,
        }
        print(summary)
        return summary


if __name__ == "__main__":
    run_demo()
