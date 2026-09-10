"""Unit tests for transfer plans and staged atomic install."""

import base64
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport import transfer
from transport.transfer import (
    TextUploadPlan,
    _remote_bash_command,
    build_file_download_plan,
    build_tar_download_plan,
    build_tar_upload_plans,
    build_text_upload_plan,
    discard_stage,
    install_staged_item,
    install_staged_path,
)


class TestRemoteBashCommand(unittest.TestCase):
    def test_base64_roundtrip_and_wrapper(self):
        script = 'echo "hello world"\n'
        cmd = _remote_bash_command(script)
        self.assertTrue(cmd.startswith("bash -c 'eval \"$(printf %s "))
        encoded = cmd.split("printf %s ")[1].split(" | base64 -d")[0]
        self.assertEqual(base64.b64decode(encoded).decode("utf-8"), script)


class TestTextUploadPlan(unittest.TestCase):
    def test_plan_fields_and_sha(self):
        payload = "αβγ-你好".encode("utf-8")
        plan = build_text_upload_plan("/home/alice/dir/file.il", payload)
        self.assertEqual(plan.remote_path, "/home/alice/dir/file.il")
        self.assertEqual(plan.remote_dir, "/home/alice/dir")
        self.assertEqual(plan.payload_size, len(payload))
        self.assertEqual(plan.payload_sha256, hashlib.sha256(payload).hexdigest())
        self.assertTrue(plan.remote_command.startswith("bash -c"))
        self.assertIn(".vbtmp-", plan.work_path)

    def test_invalid_remote_path_raises(self):
        with self.assertRaises(ValueError):
            build_text_upload_plan("/home/alice/", b"x")

    def test_persistent_command_embeds_payload_and_path(self):
        plan = build_text_upload_plan("/tmp/x.txt", b"abc")
        cmd = plan.persistent_command(b"abc")
        self.assertIn("printf %s", cmd)
        self.assertIn("base64 -d", cmd)
        self.assertIn(plan.remote_path, cmd)


class TestDownloadPlans(unittest.TestCase):
    def test_file_download_plan_staging(self):
        local = Path("/tmp/out/dst.bin")
        plan = build_file_download_plan("/remote/a/dst.bin", local)
        self.assertEqual(plan.local_path, local)
        self.assertEqual(plan.staged_item, plan.stage_path / "dst.bin")
        self.assertTrue(plan.stage_path.parent == local.parent)

    def test_tar_download_plan(self):
        local = Path("/tmp/out/psf_dir")
        plan = build_tar_download_plan("tar", "/remote/runs/psf_dir", local)
        self.assertEqual(plan.local_command, ("tar", "xzf", "-"))
        self.assertEqual(plan.staged_item, plan.stage_path / "psf_dir")
        self.assertTrue(plan.remote_command.startswith("bash -c"))

    def test_tar_download_invalid_path_raises(self):
        with self.assertRaises(ValueError):
            build_tar_download_plan("tar", "/", Path("/tmp/out"))


class TestTarUploadPlans(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "a.txt").write_text("aaa", encoding="utf-8")
        (self.root / "b.txt").write_text("bbb", encoding="utf-8")

    def test_single_file_plan_shape(self):
        (plan,) = build_tar_upload_plans("tar", [(self.root / "a.txt", "/home/u/a.txt")])
        self.assertEqual(plan.file_count, 1)
        self.assertEqual(plan.remote_dir, "/home/u")
        self.assertEqual(plan.local_command[-1], "a.txt")
        self.assertIn("-C", plan.local_command)
        self.assertTrue(plan.remote_command.startswith("bash -c"))

    def test_duplicate_remote_target_raises(self):
        with self.assertRaises(ValueError):
            build_tar_upload_plans("tar", [
                (self.root / "a.txt", "/home/u/a.txt"),
                (self.root / "b.txt", "/home/u/a.txt"),
            ])

    def test_grouping_by_remote_dir_and_parent(self):
        other = Path(tempfile.mkdtemp())
        (other / "c.txt").write_text("ccc", encoding="utf-8")
        plans = build_tar_upload_plans("tar", [
            (self.root / "a.txt", "/home/u/a.txt"),
            (self.root / "b.txt", "/home/u/b.txt"),
            (other / "c.txt", "/home/u/sub/c.txt"),
        ])
        self.assertEqual(len(plans), 2)
        self.assertEqual(sum(p.file_count for p in plans), 3)

    def test_same_basename_different_targets_partitioned(self):
        plans = build_tar_upload_plans("tar", [
            (self.root / "a.txt", "/home/u/x/a.txt"),
            (self.root / "a.txt", "/home/u/y/a.txt"),
        ])
        self.assertEqual(len(plans), 2)


class TestStagedInstall(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.stage = self.root / "stage"
        self.stage.mkdir()

    def test_fresh_file_install(self):
        staged = self.stage / "dst.txt"
        staged.write_text("new", encoding="utf-8")
        target = self.root / "dst.txt"
        install_staged_item(self.stage, staged, target)
        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        self.assertFalse(self.stage.exists())

    def test_replace_existing_file_removes_backup(self):
        target = self.root / "dst.txt"
        target.write_text("old", encoding="utf-8")
        staged = self.stage / "dst.txt"
        staged.write_text("new", encoding="utf-8")
        install_staged_item(self.stage, staged, target)
        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        self.assertEqual([p.name for p in self.root.iterdir()], ["dst.txt"])

    def test_replace_existing_directory(self):
        target = self.root / "dst"
        target.mkdir()
        (target / "old.txt").write_text("old", encoding="utf-8")
        staged = self.stage / "dst"
        staged.mkdir()
        (staged / "new.txt").write_text("new", encoding="utf-8")
        install_staged_item(self.stage, staged, target)
        self.assertEqual((target / "new.txt").read_text(encoding="utf-8"), "new")
        self.assertFalse((target / "old.txt").exists())

    def test_failure_rolls_back_previous_target(self):
        target = self.root / "dst.txt"
        target.write_text("old", encoding="utf-8")
        staged = self.stage / "missing.txt"  # does not exist -> rename fails
        with self.assertRaises(FileNotFoundError):
            install_staged_item(self.stage, staged, target)
        self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_install_staged_path_wrapper(self):
        from transport.transfer import TarDownloadPlan
        target = self.root / "final"
        target.write_text("old", encoding="utf-8")
        plan = TarDownloadPlan(
            remote_command="", local_command=("tar", "xzf", "-"),
            remote_path="/x", local_path=target,
            stage_path=self.stage, staged_item=self.stage / "final",
        )
        (self.stage / "final").write_text("new", encoding="utf-8")
        install_staged_path(plan)
        self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_discard_stage(self):
        self.assertTrue(self.stage.exists())
        discard_stage(self.stage)
        self.assertFalse(self.stage.exists())
        discard_stage(self.stage)  # no-op
        self.assertFalse(self.stage.exists())


if __name__ == "__main__":
    unittest.main()
