# fake Virtuoso（lab 测试替身）

> 维护者：Codex（IT 维护）
> 定位：替代 **Virtuoso/CIW 本身**，让**真实项目代码**完整跑通。
> 最近更新：2026-09-20 —— 首版，核心语义已对真机 IC6.1.8（wsl-gent）校准，
> 端到端回归 `e2e_check.py` 全绿。

## 1. 它是什么 / 不是什么

**是**：CIW 侧行为的测试替身 —— 拉起真 daemon、读 daemon stdout 上的 SKILL 文本、
按真机结果执行、按真机帧格式（`02/15 + %L + 1e`）回写，并在 log 请求时维护
CDS.log 字节偏移语义。

**不是**：fake daemon。协议端点、token 校验、帧解析、日志过滤、调度与客户端
全部使用项目原码（`src/bridge/resources/ramic_bridge_daemon_3.py`、
`src/common/skill_client.py`、`src/transport/middle.py` …）。

```text
[fake Virtuoso (fake_virtuoso.py)] --spawn--> [真 daemon（项目原码）]
          ^                                          |
          | 读 stdout: "RBDLogOn=<t|nil> <SKILL>"     | TCP 02/JSON/1e
          | 执行: skill_ops.eval_expr()               v
          +-- 回帧: 02 + %L(value) + 1e          [真 middle / 真 client]
               (+ log 元数据帧 02 + path + 1f + start + 1f + end + 1e)
```

真机 CIW 侧的对应实现：`src/bridge/resources/ramic_bridge.il`
（`RBIpcDataHandler` / `RBIpcErrHandler`）。

## 2. 快速开始（lab：w1-gent ~ w4-gent）

```bash
# 部署（首次）
ssh w1-gent 'sudo mkdir -p /opt/fake/virtuoso && sudo chown dev:dev /opt/fake/virtuoso'
scp test/semi/fakevirt/fake_virtuoso.py test/semi/fakevirt/skill_ops.py \
    src/bridge/resources/ramic_bridge_daemon_3.py w1-gent:/opt/fake/virtuoso/

# 启动（labns 内，监听 0.0.0.0 供 Windows 直连）
ssh w1-gent 'mkdir -p /home/dev/.virtuoso-bridge/vb-lab1/tmp && \
    sudo ip netns exec labns nohup python3 /opt/fake/virtuoso/fake_virtuoso.py \
    --daemon /opt/fake/virtuoso/ramic_bridge_daemon_3.py \
    --bind 0.0.0.0 --port 65131 --token vb-lab1 \
    --temp-dir /home/dev/.virtuoso-bridge/vb-lab1/tmp \
    > /home/dev/.virtuoso-bridge/vb-lab1/tmp/fv.log 2>&1 &'

# 客户端（真项目代码，Windows 侧）
$env:PYTHONPATH='src'
python -c "from common.skill_client import SkillClient; \
c=SkillClient(host='172.20.170.21', port=65131, token='vb-lab1'); \
print(c.execute_skill('1+2'))"

# 端到端回归（对照真机期望值，一条命令）
python test/semi/fakevirt/e2e_check.py --host 172.20.170.21 --port 65131 \
    --token vb-lab1 --hostname w1-gent
```

## 3. 支持的操作列表

状态说明：

| 状态 | 含义 |
|---|---|
| ✅ | 已实现，且已对真机 IC6.1.8（wsl-gent）校准（证据见 §6） |
| 🟡 | 已实现，尚未真机校验（暂定语义） |
| ⬜ | 未实现（按需求排期） |

> 代码侧真源：`skill_ops.py` 的 `OPS` 注册表；新增操作必须同步更新本表。

| # | 语法 | 示例 | 真机结果（`%L` 线上格式） | 状态 |
|---|---|---|---|---|
| 1 | 整数字面量 | `42` | `42` | ✅ |
| 2 | 浮点字面量 | `1.5` | `1.5` | ✅ |
| 3 | 字符串字面量 | `"hi"` | `"hi"`（带引号） | ✅ |
| 4 | `t` / `nil` | `t` | `t` / `nil` | ✅ |
| 5 | 四则运算（整数除法=向零截断） | `1+2`、`1/2`、`-7/2`、`1.0/2` | `3`、`0`、`-3`、`0.5` | ✅ |
| 6 | 跨行表达式 | `1+\n2` | `3` | ✅ |
| 7 | CIW 全局变量 | `RBDToken` | 会话注入值（如 `"vb-vblog"`） | ✅ |
| 8 | `getHostName()` | `getHostName()` | `"<主机名>"` | ✅ |
| 9 | `strcat()`（字符串入参） | `strcat("a" "b")` | `"ab"` | ✅ |
| 10 | `hiFlush()` | `hiFlush()` | `t` | ✅ |
| 11 | `printf()`（纯文本） | `printf("x\n")` | `t`；CDS.log 增量 `\o x\n` | ✅ |
| 12 | `fileLength()` | `fileLength("/tmp/f")` | 文件字节数 | ✅ |
| 13 | `hiGetLogFileName()` | `hiGetLogFileName()` | CDS.log 路径 | ✅ |
| 14 | `list()` | `list(1 2)` | `(1 2)` | ✅ |
| 15 | 错误：未定义函数 | `boom()` | `("eval" 0 t nil ("*Error* eval: undefined function" boom))` | ✅ |
| 16 | 错误：未绑定变量 | `zzz` | `("eval" 0 t nil ("*Error* eval: unbound variable" zzz))` | ✅ |
| 17 | 错误：`strcat` 类型 | `strcat(1 2)` | `("strcat" 0 t nil ("*Error* strcat: argument #1 should be either a string or a symbol (type template = \"S\")" 1))` | ✅ |
| 18 | 错误：文件不存在 | `fileLength("/tmp/no-such")` | `("fileLength" 0 t nil ("*Error* fileLength: no such file or directory" "/tmp/no-such"))` | ✅ |

### 已知限制（v0）

- **多语句/赋值/变量绑定**（如 `x = 1` 然后引用 `x`）未实现 → 需要时按需求排期。
- `printf` 不支持格式指令（`%s`/`%L`/`%d` 等）。
- `strcat` 仅接受字符串；符号字面量（`'sym`）与符号入参未实现。
- 其它 SKILL 内建函数未实现（未注册即返回真机风格"undefined function"错误）。
- CDS.log 是 fake 文件（`<temp-dir>/CDS.log`），只保证 log 链路的字节区间语义。

## 4. 真机行为校验流程（wsl-gent）

新增操作前先拿真结果，再实现：

```bash
# 1) 取真机证据（探针跑在真机上，直连 65121 端口）
ssh wsl-gent 'mkdir -p ~/.virtuoso-bridge/vblog/tmp'
scp test/semi/fakevirt/probe_real.py wsl-gent:~/.virtuoso-bridge/vblog/tmp/probe_real.py
ssh wsl-gent 'python3 ~/.virtuoso-bridge/vblog/tmp/probe_real.py \
    --port 65121 --token vb-vblog "1+2" "1/2" "boom()"'

# 2) 记录证据（贴进 §6 验证记录），实现并更新 §3 表格

# 3) 回归（Windows 侧，对照真机期望值）
python test/semi/fakevirt/e2e_check.py --host 172.20.170.21 --port 65131 \
    --token vb-lab1 --hostname w1-gent
```

## 5. 需求格式（提交给维护者）

```text
操作名：
示例调用：
期望结果：
使用场景（哪个测试/TB 依赖它）：
备注（超时/副作用/日志行为等）：
```

维护者据此在真机取证据、实现、回归，并更新 §3 表格。

## 6. 验证记录

### 2026-09-20 首轮（真机 IC6.1.8 @ wsl-gent，daemon 65121 / token vb-vblog）

```text
'1+2'                 -> OK  3
'"hi"'                -> OK  "hi"
't'                   -> OK  t
'nil'                 -> OK  nil
'(1+2)*3'             -> OK  9
'1/2'                 -> OK  0          # 整数除法（向零截断）
'-7/2'                -> OK  -3
'1.0/2'               -> OK  0.5        # 涉及浮点则浮点除
'1.5'                 -> OK  1.5
'strcat("a" "b")'     -> OK  "ab"
'getHostName()'       -> OK  "GLIS-DESKTOP"
'list(1 2)'           -> OK  (1 2)
'hiFlush()'           -> OK  t
'RBDToken'            -> OK  "vb-vblog"
'hiGetLogFileName()'  -> OK  "/home/Gent/project/vblog/CDS.log"
'fileLength("/tmp/probe_len.txt")' -> OK  5
'printf("probe-log\n")'  -> LOG  t | log='\o probe-log\n'
'boom()'              -> ERR  ("eval" 0 t nil ("*Error* eval: undefined function" boom))
'zzz'                 -> ERR  ("eval" 0 t nil ("*Error* eval: unbound variable" zzz))
'strcat(1 2)'         -> ERR  ("strcat" 0 t nil ("*Error* strcat: argument #1 should be either a string or a symbol (type template = \"S\")" 1))
'fileLength("/tmp/nonexistent-xyz")' -> ERR  ("fileLength" 0 t nil ("*Error* fileLength: no such file or directory" "/tmp/nonexistent-xyz"))
```

同轮 fake（w1-gent lab）`e2e_check.py` 复核：**ALL PASS**（9 成功用例 +
4 错误结构用例 + 1 log 用例）。
