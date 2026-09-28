"""`common.config` 快照语义的**边界**契约（第六轮补测）。

为什么补：`common/config.py` 的分支覆盖长期只有 50%（`cov-main` 口径），
而未覆盖的正是**快照身份语义**——`init_config` 的"同路径幂等 / 换路径报错"、
`replace_snapshot` 在"尚未初始化且不给 path"时绑定默认路径、以及
`_freeze`/`_thaw` 对**序列**的处理。这几条是控制面/业务面共享的进程级契约，
不是实现细节：写错就会让"改注册表/配置不重载"（P-048 同类问题）再次发生。

断言口径：只断言可观察行为（返回对象身份、冻结后的可写性、抛出的错误类型与文案），
不改 `src/`；每个用例都在 setUp/tearDown 里**保存并还原**进程级快照，
避免像 P-064/P-065 那样把状态泄漏给别的用例。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common import config, paths


class _SnapshotIsolated(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = (config._snapshot_path, config._snapshot)
        self._td = tempfile.TemporaryDirectory(prefix="vb-cfg-")
        # work root 由 test/conftest.py 的 session fixture 绑定一次（产品口径：一进程一根）

    def tearDown(self) -> None:
        self._td.cleanup()
        config._snapshot_path, config._snapshot = self._saved


class TestSnapshotIdentity(_SnapshotIsolated):
    def test_init_config_same_path_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text(json.dumps({"a": 1}), encoding="utf-8")
            config._snapshot_path = None
            config._snapshot = None
            first = config.init_config(path)
            second = config.init_config(path)
            self.assertIs(first, second, "同路径重复 init 必须返回同一个快照对象")
            self.assertEqual(config.snapshot_dict(), {"a": 1})

    def test_init_config_other_path_raises(self):
        with tempfile.TemporaryDirectory() as td:
            first = Path(td) / "a.json"
            other = Path(td) / "b.json"
            first.write_text("{}", encoding="utf-8")
            other.write_text("{}", encoding="utf-8")
            config._snapshot_path = None
            config._snapshot = None
            config.init_config(first)
            with self.assertRaises(RuntimeError) as ctx:
                config.init_config(other)
            self.assertIn("already initialized", str(ctx.exception))

    def test_replace_snapshot_without_path_binds_default(self):
        config._snapshot_path = None
        config._snapshot = None
        replaced = config.replace_snapshot({"k": [1, {"n": 2}]})
        self.assertIs(config.snapshot(), replaced)
        # 已经绑定默认路径 + 已冻结 → 再用默认路径 init 必须"命中同一个快照"而不是报错
        self.assertIs(config.init_config(None), replaced)

    def test_replace_snapshot_without_path_needs_initialized_work_dir(self):
        """未初始化工作目录时**不得**隐式绑定默认路径（否则会读错别处的 config.json）。"""
        env = dict(os.environ)
        src = str(Path(__file__).resolve().parents[3] / "src")
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from common import config; config.replace_snapshot({'k': 1})",
            ],
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("work dir not initialized", result.stderr)


class TestFreezeThawSequences(_SnapshotIsolated):
    def test_freeze_turns_sequences_into_tuples_and_blocks_mutation(self):
        config._snapshot_path = None
        config._snapshot = None
        snapshot = config.replace_snapshot({"xs": [1, {"y": 2}], "t": (1, 2)})
        self.assertIsInstance(snapshot["xs"], tuple, "序列必须冻结成 tuple")
        self.assertIsInstance(snapshot["xs"][1], MappingProxyType, "嵌套映射也要冻结")
        with self.assertRaises(TypeError):
            snapshot["xs"][1]["y"] = 3
        self.assertEqual(snapshot["t"], (1, 2))

    def test_thaw_returns_mutable_plain_containers(self):
        config._snapshot_path = None
        config._snapshot = None
        config.replace_snapshot({"xs": [1, [2, 3]]})
        plain = config.snapshot_dict()
        self.assertEqual(plain, {"xs": [1, [2, 3]]})
        self.assertIsInstance(plain["xs"], list)
        plain["xs"].append(4)                      # 可变副本，不影响快照
        self.assertEqual(config.snapshot()["xs"], (1, (2, 3)))


if __name__ == "__main__":
    unittest.main()
