"""操作 × 参数覆盖矩阵（第八轮"每个可传参数"口径，v2 = AST 解析）。

v1 用正则在 TB 文本里找 ``"virtuoso.cellview.cat.create"`` 字面量；对
``OP + "lib.create"``、``f"{PREFIX}.read"``、以及 ``_op(transport, "suffix", ...)``
这类写法一律漏判 —— cellview 的 22 个 op 因此被整包误报成 NO-OP-TB。

v2 用 AST：

* 解析每个 TB 的模块级字符串常量（如 ``OP = "virtuoso.cellview."``）；
* 识别"操作载体函数"（形如 ``_op(transport, operation, **fields)`` →
  ``{"operation": OP + operation, ...}``），并解析**调用点**的 op 与实参名，
  含跨函数转发（``_value`` → ``_op`` → ``_call``）；
* 无法静态求值的表达式（变量 f-string、运行期拼接）如实记入
  ``unresolved``，**不计覆盖**。

覆盖判定（保守）：
* ``CANDIDATE``：该 op 的某个调用点显式出现该参数名（关键字实参或 payload 字典键）；
* ``GAP``：有 op 调用点但从未出现该参数；
* ``NO-OP-TB``：连 op 调用点都没有。
机器结果仍需人工/子代理复核（CANDIDATE 只证明"参数被传过"，不证明断言了语义）。

用法::

    python test/shared/runners/build_op_param_matrix.py
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "test" / "reports" / "round8"
PKG = ROOT / "src" / "pyapi" / "packages"
TB_DIRS = [
    "test/offline",
    "test/semi",
    "test/live",
    "test/shared/fixtures",
    "test/shared/runners",
]

SPEC_ATOM_RE = re.compile(r"^\|\s*([a-z][a-z0-9_]{3,})\s*\|(.+)\|\s*$", re.M)
IDENT_RE = re.compile(r"[a-z_][a-z0-9_]{1,}")


# --------------------------------------------------------------------------
# 1) 实现侧：每个 op 的请求模型字段
# --------------------------------------------------------------------------
def _const_str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def load_operations() -> dict[str, dict]:
    ops: dict[str, dict] = {}
    for path in sorted(PKG.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        classes: dict[str, ast.ClassDef] = {
            node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
        }
        entries: list[tuple[str, str, str]] = []
        for node in tree.body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, (ast.Tuple, ast.List)):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "OPERATIONS" for t in node.targets):
                continue
            for elt in node.value.elts:
                if (
                    isinstance(elt, ast.Tuple)
                    and len(elt.elts) >= 3
                    and (op := _const_str(elt.elts[0]))
                    and (method := _const_str(elt.elts[1]))
                    and isinstance(elt.elts[2], ast.Name)
                ):
                    entries.append((op, method, elt.elts[2].id))
        for op, method, model in entries:
            fields: dict[str, dict] = {}
            cls = classes.get(model)
            if cls is not None:
                for stmt in cls.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        default = None
                        if stmt.value is not None:
                            try:
                                default = ast.unparse(stmt.value)
                            except Exception:  # pragma: no cover - 防御
                                default = "?"
                        fields[stmt.target.id] = {
                            "type": ast.unparse(stmt.annotation),
                            "has_default": stmt.value is not None,
                            "default": (default or "")[:60],
                        }
            ops[op] = {
                "package": path.name,
                "method": method,
                "model": model,
                "params": fields,
            }
    return ops


def load_spec_atoms() -> dict[str, set[str]]:
    atoms: dict[str, set[str]] = {}
    pkg_keys: dict[str, set[str]] = {}
    for pkg in ("schematic", "symbol", "layout"):
        text = (PKG / f"{pkg}.py").read_text(encoding="utf-8", errors="replace")
        pkg_keys[pkg] = set(re.findall(r'cmd(?:\.get\(|\[)\s*"(\w+)"', text))
    for rel, pkg in (
        ("上层/2-schematic.md", "schematic"),
        ("上层/3-symbol.md", "symbol"),
        ("上层/4-layout.md", "layout"),
    ):
        path = ROOT / "spec" / "design-concepts" / rel
        if not path.exists():
            continue
        for op, rest in SPEC_ATOM_RE.findall(path.read_text(encoding="utf-8")):
            params = {t for t in IDENT_RE.findall(rest) if t in pkg_keys[pkg]}
            atoms.setdefault(op, set()).update(params)
    return atoms


# --------------------------------------------------------------------------
# 2) TB 侧：AST 解析 op 调用点与实参
# --------------------------------------------------------------------------
class FileAnalysis:
    """一个 TB 文件的静态解析结果。"""

    def __init__(self, rel: str, text: str) -> None:
        self.rel = rel
        self.text = text
        try:
            self.tree: ast.Module | None = ast.parse(text)
        except SyntaxError:
            self.tree = None
        self.consts: dict[str, str] = {}
        self.funcs: dict[str, ast.FunctionDef] = {}
        #: 函数名 -> 承载 operation 的形参名
        self.op_param: dict[str, str] = {}
        #: 直接构造 payload 的函数名 -> payload 里固定注入的字符串键（如 token）
        self.payload_keys: dict[str, set[str]] = {}
        #: 绑定到固定 op 的包装函数（如 _search → "virtuoso.skillref.search"）
        self.op_bindings: dict[str, set[str]] = {}
        self.calls: list[dict] = []
        self.unresolved: list[dict] = []
        #: Call 节点 -> 所在函数名（None = 模块级）；用于区分「管道行」与真正的未解析调用点
        self.enclosing: dict[int, str | None] = {}
        if self.tree is not None:
            self._collect()

    # -- 模块级字符串常量 ------------------------------------------------
    def _collect(self) -> None:
        assert self.tree is not None
        for func in [n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]:
            for node in ast.walk(func):
                self.enclosing[id(node)] = func.name
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                value = self._eval_str(node.value)
                if value is not None:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.consts[target.id] = value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                value = self._eval_str(node.value) if node.value is not None else None
                if value is not None:
                    self.consts[node.target.id] = value
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                self.funcs[node.name] = node
        self._find_direct_operation_funcs()
        self._resolve_calls()

    def _eval_str(self, node: ast.AST | None) -> str | None:
        if node is None:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self.consts.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._eval_str(node.left)
            right = self._eval_str(node.right)
            return None if left is None or right is None else left + right
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                else:
                    return None
            return "".join(parts)
        return None

    @staticmethod
    def _func_params(func: ast.FunctionDef) -> list[str]:
        return [a.arg for a in func.args.args]

    def _find_direct_operation_funcs(self) -> None:
        """body 里直接构造 {"operation": <expr>} 的函数 → 它的 op 形参。"""
        assert self.tree is not None
        for func in self.funcs.values():
            params = set(self._func_params(func))
            for node in ast.walk(func):
                if not isinstance(node, ast.Dict):
                    continue
                for key, value in zip(node.keys, node.values):
                    if not (isinstance(key, ast.Constant) and key.value == "operation"):
                        continue
                    names = {
                        n.id
                        for n in ast.walk(value)
                        if isinstance(n, ast.Name) and n.id in params
                    }
                    if len(names) == 1:
                        self.op_param[func.name] = names.pop()
                    keys = {
                        k.value
                        for k in node.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    }
                    self.payload_keys.setdefault(func.name, set()).update(keys)

        # 传递闭包：_value(operation) -> _op(operation, **fields) -> _call...
        changed = True
        while changed:
            changed = False
            for func in self.funcs.values():
                if func.name in self.op_param:
                    continue
                params = self._func_params(func)
                for node in ast.walk(func):
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                        continue
                    callee = self.op_param.get(node.func.id)
                    if callee is None:
                        continue
                    for idx, arg in enumerate(node.args):
                        if idx < len(params) and params[idx] == callee and isinstance(arg, ast.Name):
                            self.op_param[func.name] = arg.id
                            changed = True
                            break
                    for kw in node.keywords:
                        if (
                            kw.arg == callee
                            and isinstance(kw.value, ast.Name)
                            and kw.value.id in params
                        ):
                            self.op_param[func.name] = kw.value.id
                            changed = True
                    if func.name in self.op_param:
                        break
        self._resolve_op_bindings()

    def _resolve_op_bindings(self) -> None:
        """包装函数：内部用**字面量** op 调操作载体 → 绑定该 op。"""
        assert self.tree is not None
        changed = True
        while changed:
            changed = False
            for func in self.funcs.values():
                if func.name in self.op_param:
                    continue
                bound: set[str] = set(self.op_bindings.get(func.name, set()))
                before = len(bound)
                for node in ast.walk(func):
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                        continue
                    callee = node.func.id
                    if callee in self.op_param:
                        target = self.op_param[callee]
                        sub = self.funcs.get(callee)
                        idx = self._func_params(sub).index(target) if sub else None
                        expr = None
                        if idx is not None and idx < len(node.args):
                            expr = node.args[idx]
                        for kw in node.keywords:
                            if kw.arg == target:
                                expr = kw.value
                        if expr is not None:
                            resolved = self._resolve_op_expr(expr)
                            if resolved:
                                bound.add(resolved)
                    elif callee in self.op_bindings:
                        bound |= self.op_bindings[callee]
                if len(bound) != before:
                    self.op_bindings[func.name] = bound
                    changed = True
        # 只保留非空绑定
        self.op_bindings = {k: v for k, v in self.op_bindings.items() if v}

    # -- 遍历调用点 -------------------------------------------------------
    def _resolve_op_expr(self, node: ast.AST) -> str | None:
        raw = self._eval_str(node)
        if raw is None:
            return None
        if raw in KNOWN_OPS:
            return raw
        prefixes = {v for v in self.consts.values() if v.endswith(".")}
        for prefix in prefixes:
            if prefix + raw in KNOWN_OPS:
                return prefix + raw
        suffix_hits = [op for op in KNOWN_OPS if op.endswith("." + raw)]
        if len(suffix_hits) == 1:
            return suffix_hits[0]
        return None

    def _implicit_params(self, func_name: str) -> set[str]:
        """helper 链固定注入的 payload 键（token 等），随转发闭包合并。"""
        found: set[str] = set()
        seen: set[str] = set()
        todo = [func_name]
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            found.update(self.payload_keys.get(name, set()))
            func = self.funcs.get(name)
            if func is None:
                continue
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in self.op_param:
                        todo.append(node.func.id)
        return found - {"operation"}

    def _resolve_calls(self) -> None:
        assert self.tree is not None

        def param_names(call: ast.Call) -> set[str]:
            names = {kw.arg for kw in call.keywords if kw.arg}
            for arg in call.args:
                if isinstance(arg, ast.Dict):
                    names.update(
                        k.value
                        for k in arg.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    )
            return names

        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            # A) payload 字典直接出现在调用实参里
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    keys = [
                        k.value
                        for k in arg.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    ]
                    for key, value in zip(arg.keys, arg.values):
                        if isinstance(key, ast.Constant) and key.value == "operation":
                            op = self._resolve_op_expr(value)
                            params = set(keys) - {"operation"}
                            self._record(op, node, params, "payload-dict")
            # B) 调用"操作载体函数"
            if isinstance(node.func, ast.Name) and node.func.id in self.op_param:
                target = self.op_param[node.func.id]
                func = self.funcs.get(node.func.id)
                idx = self._func_params(func).index(target) if func else None
                expr = None
                if idx is not None and idx < len(node.args):
                    expr = node.args[idx]
                for kw in node.keywords:
                    if kw.arg == target:
                        expr = kw.value
                if expr is None:
                    continue
                self._record(
                    self._resolve_op_expr(expr),
                    node,
                    (param_names(node) | self._implicit_params(node.func.id)) - {target},
                    f"helper:{node.func.id}",
                    raw=ast.get_source_segment(self.text, expr),
                )
            # C) 调用"绑定固定 op 的包装函数"（如 _search/_info）
            elif isinstance(node.func, ast.Name) and node.func.id in self.op_bindings:
                for bound_op in sorted(self.op_bindings[node.func.id]):
                    self._record(
                        bound_op,
                        node,
                        param_names(node) | self._implicit_params(node.func.id),
                        f"wrapper:{node.func.id}",
                    )

    def _record(self, op: str | None, node: ast.Call, params: set[str], how: str,
                raw: str | None = None) -> None:
        line = getattr(node, "lineno", 0)
        if op is None:
            # 「管道行」＝该调用点所在函数**自己**就是 op 载体（形如 _op(transport, operation, …)
            # 把形参原样转发）。它把真实 op 交给调用者，本身不代表漏测，单列一类。
            owner = self.enclosing.get(id(node))
            plumbing = bool(owner and owner in self.op_param)
            self.unresolved.append({"line": line, "how": how, "raw": (raw or "")[:120],
                                    "params": sorted(p for p in params if p),
                                    "enclosing": owner, "plumbing": plumbing})
            return
        self.calls.append({"op": op, "line": line, "how": how,
                           "params": sorted(p for p in params if p)})


KNOWN_OPS: set[str] = set()


def main() -> int:
    global KNOWN_OPS
    OUT.mkdir(parents=True, exist_ok=True)
    ops = load_operations()
    spec_atoms = load_spec_atoms()
    KNOWN_OPS = set(ops) | set(spec_atoms)
    print(f"实现 OPERATIONS: {len(ops)} 个 op；spec 原子表: {len(spec_atoms)} 个原子 op")

    analyses: dict[str, FileAnalysis] = {}
    for rel in TB_DIRS:
        for path in (ROOT / rel).rglob("*.py"):
            rel_path = path.relative_to(ROOT).as_posix()
            analyses[rel_path] = FileAnalysis(
                rel_path, path.read_text(encoding="utf-8", errors="replace"))

    op_sites: dict[str, set[str]] = defaultdict(set)
    op_files: dict[str, set[str]] = defaultdict(set)
    op_param_sites: dict[tuple[str, str], set[str]] = defaultdict(set)
    unresolved_all: list[dict] = []
    for rel, analysis in analyses.items():
        for call in analysis.calls:
            where = f"{rel}:{call['line']}"
            op_sites[call["op"]].add(where)
            op_files[call["op"]].add(rel)
            for param in call["params"]:
                op_param_sites[(call["op"], param)].add(where)
        for item in analysis.unresolved:
            unresolved_all.append({"file": rel, **item})

    rows: list[dict] = []
    for op, info in sorted(ops.items()):
        sites = sorted(op_sites.get(op, set()))
        for param, meta in sorted(info["params"].items()):
            hits = sorted(op_param_sites.get((op, param), set()))
            generic = param in ("timeout",)  # 通用字段：由跨 op 的合同用例承担
            rows.append({
                "op": op,
                "layer": "request",
                "package": info["package"],
                "param": param,
                "required": not meta["has_default"],
                "type": " ".join(meta["type"].split()),
                "op_tb_files": len(op_files.get(op, set())),
                "op_sites": sites[:8],
                "param_hits": hits[:8],
                "status": "CANDIDATE" if hits else ("GAP" if sites else "NO-OP-TB"),
                "generic": generic,
            })
    for atom, params in sorted(spec_atoms.items()):
        files = sorted(rel for rel, a in analyses.items() if atom in a.text)
        for rel in files:  # 原子 op 以 `"cmd": "<op>"` 形式出现，单独记录
            op_files[atom].add(rel)
            op_sites[atom].add(rel)
        for param in sorted(params):
            pattern = re.compile(rf'["\']{re.escape(param)}["\']|{re.escape(param)}\s*=')
            hits = [rel for rel in files if pattern.search(analyses[rel].text)]
            rows.append({
                "op": atom,
                "layer": "atomic",
                "package": "",
                "param": param,
                "required": False,
                "type": "spec-table",
                "op_tb_files": len(files),
                "op_sites": files[:8],
                "param_hits": hits[:8],
                "status": "CANDIDATE" if hits else ("GAP" if files else "NO-OP-TB"),
                "generic": False,
            })

    (OUT / "op-param-matrix.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    op_coverage = {
        op: {
            "package": ops[op]["package"] if op in ops else "(atomic)",
            "files": sorted(op_files.get(op, set())),
            "call_sites": len(op_sites.get(op, set())),
        }
        for op in sorted(KNOWN_OPS)
    }
    (OUT / "op-coverage.json").write_text(
        json.dumps(op_coverage, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    gaps = [r for r in rows if r["status"] != "CANDIDATE"]
    generic_gaps = [r for r in gaps if r.get("generic")]
    open_gaps = [r for r in gaps if not r.get("generic")]
    by_status = defaultdict(int)
    for row in rows:
        by_status[row["status"]] += 1
    lines = [
        "# 操作 × 参数覆盖矩阵（机器，AST 解析；**不是覆盖结论**）",
        "",
        f"- 条目 {len(rows)}：CANDIDATE {by_status['CANDIDATE']} / GAP {by_status['GAP']} "
        f"/ NO-OP-TB {by_status['NO-OP-TB']}",
        f"- 非 CANDIDATE 中：通用 `timeout` 字段 {len(generic_gaps)} 条（由 "
        f"`test/offline/unit/test_param_timeout_contract.py` 的 79/79 op 合同承担）；"
        f"其余 {len(open_gaps)} 条为逐 op 缺口。",
        f"- 无法静态解析的调用点 {len(unresolved_all)} 个 = 管道行 "
        f"{sum(1 for u in unresolved_all if u.get('plumbing'))}（op 载体内部把形参转发，"
        f"真值在调用点已解析）+ **待人工复核 {sum(1 for u in unresolved_all if not u.get('plumbing'))}**"
        "（不计覆盖）",
        "- CANDIDATE = 参数名在目标 op 的调用点出现；是否断言语义仍要逐条看 TB 判据。",
        "- op 调用点清单见 `op-coverage.json`；未解析明细见本文件末尾。",
        "",
        "## 非 CANDIDATE（按 op 分组）",
        "",
    ]
    by_op: dict[str, list[dict]] = defaultdict(list)
    for row in open_gaps:
        by_op[row["op"]].append(row)
    for op in sorted(by_op):
        lines.append(f"### `{op}`")
        lines.append("")
        for row in by_op[op]:
            lines.append(
                f"- [{row['status']}] `{row['param']}` ({row['type'][:40]}, "
                f"required={row['required']}) — op_tb_files={row['op_tb_files']}"
            )
        lines.append("")
    if unresolved_all:
        plumbing = [u for u in unresolved_all if u.get("plumbing")]
        review = [u for u in unresolved_all if not u.get("plumbing")]
        lines.append(f"## 未解析调用点（机器，不计覆盖）")
        lines.append("")
        lines.append(f"### A. 待人工复核（{len(review)}）——非管道行，需逐条确认是真实调用点还是辅助函数")
        lines.append("")
        for item in review[:400]:
            lines.append(
                f"- {item['file']}:{item['line']} `{item['raw']}` "
                f"(how={item['how']}, enclosing={item.get('enclosing')}, "
                f"params={','.join(item['params'][:6])})"
            )
        lines.append("")
        lines.append(f"### B. 管道行（{len(plumbing)}）——op 载体内部转发形参，真值在调用点已解析，不构成漏测")
        lines.append("")
        for item in plumbing[:400]:
            lines.append(
                f"- {item['file']}:{item['line']} `{item['raw']}` "
                f"(enclosing={item.get('enclosing')}, params={','.join(item['params'][:6])})"
            )
        lines.append("")
    (OUT / "op-param-matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"矩阵 {len(rows)} 条：CANDIDATE {by_status['CANDIDATE']} / GAP {by_status['GAP']} "
          f"/ NO-OP-TB {by_status['NO-OP-TB']}；未解析调用点 {len(unresolved_all)}")
    no_tb = [op for op in ops if not op_files.get(op)]
    print(f"零调用点的业务 op：{len(no_tb)}")
    for op in sorted(no_tb)[:30]:
        print(f"  - {op}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
