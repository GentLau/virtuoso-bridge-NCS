# 测试体系（test/）

按等级组织：函数级 → 集成级 → 场景级 → 真实场景级，验收中层（transport）、底层（bridge）、注册流程（transport/register）与注册页面（server）。

```text
test/
  unit/         函数级：纯函数、数据模型、解析、带 mock 的传输/注册分支
  integration/  集成级：真实 socket 的假 daemon、daemon 子进程、wire 协议
  scenario/     场景级：本地六步注册全流程、多用户 token 隔离
  e2e/          真实场景级：wsl-gent 真实 Virtuoso + OpenSSH/Paramiko
test_bak/       旧 tests/ 内容 + 调试期临时文件（不参与常规运行）
```

## 运行

```bash
# 函数级
python -m unittest discover -s test/unit -p "test_*.py" -v

# 集成级
python -m unittest discover -s test/integration -p "test_*.py" -v

# 场景级
python -m unittest discover -s test/scenario -p "test_*.py" -v

# 真实场景级（需要 wsl-gent + 运行中的 Virtuoso）
$env:VB_E2E='1'; python -m unittest discover -s test/e2e -p "test_*.py" -v
```

## 覆盖率

```bash
coverage erase
coverage run --source=src -m unittest discover -s test/unit -p "test_*.py"
coverage run -a --source=src -m unittest discover -s test/integration -p "test_*.py"
coverage run -a --source=src -m unittest discover -s test/scenario -p "test_*.py"
$env:VB_E2E='1'; coverage run -a --source=src -m unittest discover -s test/e2e -p "test_*.py"
coverage report --skip-empty --show-missing
```

最新数字与未覆盖原因见 `doc/测试覆盖报告.md`。

## e2e 场景覆盖

```text
六步注册 apply(申请+本地校验+探测+部署) → load(CIW RBStop+load)
  → verify(命令冒烟+Skill冒烟+token校验+banner比对) → commit(唯一落盘)
  → execute_skill(value+CDS.log增量) → run_command
  → upload/download(sha256 校验) → parallel=True 时间区间重叠验证
  → Paramiko 后端：run_command + upload_text + cat 校验
```
