# 机制：多行 SKILL 里 `errset(progn ...)` 的陷阱

> 日期：2026-09-21
> 发现场景：symbol 业务包 `read` 的清理改造（`src/pyapi/packages/symbol.py`）
> 影响面：所有通过 `execute_skill` 发送**含换行** SKILL 的上层业务包

## 1. 现象

真机（Virtuoso 6.1.8）执行：

```
vbCollected = errset(progn
  vbResult = nil
  foreach(...)
  vbResult)
```

报错（daemon 日志）：

```
*Error* errset: too many arguments (at most 2 expected, 8 given)
```

同一段逻辑写成单行（`errset(progn(a b c))`）却正常；写成

```
vbCollected = errset(progn(vbResult = nil
  foreach(...)
  vbResult))
```

也正常。

## 2. 原因

bridge daemon 有两条发送路径（`src/bridge/resources/ramic_bridge_daemon_27.py`）：

| 代码形态 | 发送方式 |
|---|---|
| 单行（无 `\n`） | `let(((__vb_r <code>)) hiFlush() __vb_r)` 直接进 CIW |
| 含换行 | 落盘成 `.il`，内容为 `_vb_eval_result = progn(\n<code>\n)`，再 `load("<file>")` |

走落盘路径时，`progn` 的关键字形态会被 reader 展开，`errset` 会把 `progn` 的**各条语句当成独立实参**，于是超出 `errset(expr [print])` 的 2 参上限而报错。

## 3. 规避写法

1. 多行代码里 **`progn(` 后面紧跟第一条语句**，整段用 `))` 收尾；
2. 或把要保护的整段代码放在同一行；
3. 或用 lambda 包一层：`errset(funcall(lambda(() stmt1 stmt2)))`（已实测可用）；
4. 或直接用 `unwindProtect(body cleanup)` 做资源清理（同样遵守第 1 条写法）。

## 4. 已验证的对照实验

| 写法（多行 SKILL） | 结果 |
|---|---|
| `a = errset(progn(1 2 3))`（同一行） | success |
| `a = errset(progn` + 换行 + 语句 | **error（8 个实参）** |
| `a = errset(progn(println("a")` + 换行 + 语句 + `))` | success |
| `a = errset(funcall(lambda(() ...)))` | success |
| `unwindProtect(progn(1 2 3) cleanup)`（同一行） | success |

## 5. 代码侧裁决（2026-09-21）

该现象已复现，但**不是 bridge daemon 的单行/多行分支缺陷**。

报告中的失败写法是：

```skill
a = errset(progn
  1
  2
  3)
```

这里 `progn` 后缺少 `(`。SKILL reader 会把它解析成
`errset(progn 1 2 3)`：`progn` 是第一个实参，后面的表达式是额外实参，
因此得到 `too many arguments`。同样的问题与是否含换行无关，直接在普通
`.il` 文件中 `load()` 也会以相同方式失败。

对照验证：

| 输入 | 结果 |
|---|---|
| 普通 `.il` 文件中的 `errset(progn` + 换行 + 多个表达式 | `errset: too many arguments` |
| 普通 `.il` 文件中的 `errset(progn(1` + 换行 + 继续写表达式 | success |
| bridge 单行 `errset(progn(1 2 3))` | success |

结论：daemon 不需要为这个写法做兼容；上层应统一写成
`errset(progn(<第一条语句>`。本报告的上文保留为写法陷阱说明，不按
bridge 缺陷处理。

## 6. 补充发现：合法单行 SKILL 的内联包装缺口（已修）

报告本身是非法 SKILL，但按“合法 SKILL 不应受单行/多行内部实现影响”的
契约继续实测时，确实发现了另一个真实缺口：

```skill
a = 1 b = 2 a+b
```

```skill
a = 1 ; comment
```

这两段都是合法 SKILL。旧单行路径把它们塞进
`let(((__vb_r <code>)) hiFlush() __vb_r)`，等价于把整段文本当成一个
绑定值；多顶层表达式会触发 `let: illegal binding form`，行尾注释会吃掉
包装用的闭括号，触发 `let: too few arguments`。多行路径因为走
`_vb_eval_result = progn(...)` 文件加载，没有这个问题。

修复后的单行路径统一为：

```skill
let(((__vb_r progn(<code>
))) hiFlush() __vb_r)
```

即：单行/多行都按 `progn(<code>)` 捕获最后一个表达式；`<code>` 后的换行
终止行尾 `;` 注释，不再让它吞掉 daemon 自己的闭括号。`ramic_bridge_daemon_3.py`
和 `ramic_bridge_daemon_27.py` 已同步。

验证：

- 真机矩阵 `test/tb/skill_syntax_matrix_tb.py`：修复前 **8/10**，
  失败项正是单行多表达式和单行行尾注释；修复后 **10/10**。
- `test/integration/test_daemon_handler.py` 增加 py3/py27 双跑用例，
  固定检查 `progn(<code>\n)` 包装。
- 该修复不会让原本非法的 `errset(progn` 形式变合法；它只保证合法 SKILL
  不再因为 daemon 的内部包装方式而失败。
