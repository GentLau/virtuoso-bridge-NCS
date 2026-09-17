"""``common``：四层共享的基座模块（不属于任何一层）。

- 只放**进程级环境**：工作根与由其派生的只读路径；
- 不放请求级数据（用户、token、业务参数、请求级子目录）；
- 不 import 任何业务层（``transport``/``server``/``pyapi``/``bridge``），
  因此四层 import 它都不算层级倒置。
"""
from __future__ import annotations

from common.paths import (
    artifact_dir,
    command_log_file,
    default_work_dir,
    init_work_dir,
    log_dir,
    override_work_dir_for_tests,
    registry_path,
    server_config_path,
    sub_dir,
    temp_dir,
    work_root,
)

__all__ = [
    "artifact_dir",
    "command_log_file",
    "default_work_dir",
    "init_work_dir",
    "log_dir",
    "override_work_dir_for_tests",
    "registry_path",
    "server_config_path",
    "sub_dir",
    "temp_dir",
    "work_root",
]
