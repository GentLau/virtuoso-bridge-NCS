# 真机 pytest（`test/live/e2e/`）

原来的 `test/e2e/`，需要**真实 Virtuoso / 真实靶机**，因此归入 TB 世界，不参与默认 CI。

```powershell
# 全部真机用例（未设置环境变量时按环境条件跳过）
python -m pytest test/live/e2e -v

# 或按 unittest 入口（与原用法一致）
$env:VB_E2E='1'; python -m unittest discover -s test/live/e2e -p "test_*.py"
```

| 文件 | 需要 |
|---|---|
| `test_e2e_live.py` | `wsl-gent` 上的 bridge daemon |
| `test_business_local_live.py` | 本机/WSL local 模式 + `VB_E2E_LOCAL=1` |
| `test_business_remote_live.py` | `VB_E2E=1` + `wsl-gent` 上的多实例 daemon |

路径与产物规则见 [`../../docs/文件使用规范.md`](../../docs/文件使用规范.md)；真机准入见 [`../transport/README.md`](../transport/README.md)。
