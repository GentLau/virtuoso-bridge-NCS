# skillref：远端取数成本评估（要不要预加载 / 要不要建索引）

> 日期：2026-09-21｜环境：8127（token `vb-vblog`）→ `wsl-gent`，IC618 文档树
> 关联：`spec/design-concepts/上层/9-skillref.md`（Draft v5）§3 / §4.6

## 0. 结论（先回答两个问题）

1. **不需要任何预加载**。skillref 的两个操作都是"按请求取数"：
   远端模式每次拉 `.fnd`（2.4 MB）或 `.tgf`（924 KB）+ 命中的单个 HTML；本地模式直接读文件。
2. **不需要建索引**。旧项目确实在本地建过两样东西——`.fnd` 下载缓存
   （`src_bak/.../basic/bridge.py:920 cache_root("skill_finder")/<host>`）与文档全文
   SQLite 索引（`src_bak/.../docs_search.py:24/965` schema v3 + manifest）——本设计两样都不做（无状态）。
   8123 那种"启动时把 9503 条加载进内存"属于常驻服务的进程内缓存，不是索引，也不在业务链路里。
3. 远端取数的量级已被实测钉死：**单次调用 1–5 秒、传输 0.2–2.4 MB**，
   唯一注意点是正文层的**逐候选下载**（每文件 ≈1.9 s）。

## 1. 文档树到底有多大（远端实测）

整树 6.5 GB / 71 319 文件，但**可搜索的文本子集只有 223.8 MB（≈3%）**：

| 后缀 | 文件数 | 体积 | 说明 |
|---|---:|---:|---|
| `.html` | 8 597 | 209.6 MB | 正文主体 |
| `.json` | 170 | 8.4 MB | 辅助数据 |
| `.xml` | 497 | 4.0 MB | 辅助数据 |
| `.tgf` | 74 | 1.5 MB | 主题表（其中 `api_more_info.tgf` 924 KB 是入口） |
| `.txt` | 68 | 0.2 MB | — |
| `.htm` | 20 | <0.1 MB | — |
| **小计** | **9 426** | **223.8 MB** | 检索只需扫这一部分 |

其余 6.3 GB 是**非文本资产**，与检索无关：`.mp4` 1 811.5 MB / `.gif` 1 553.4 MB /
`.pdf` 765.5 MB / `.png` 733.2 MB / `.cfs` 594.8 MB（Cadence 自带索引二进制，2 个文件）/
`.zip` 355.3 MB / `.jpg` 114.3 MB。

## 2. 单步实测（8127 → wsl-gent）

| 步骤 | 接口 | 体积 | 实测耗时 |
|---|---|---:|---:|
| 词条层：递归拉 `<doc_root>/finder/SKILL`（37 个 `.fnd`） | `file.download(recursive)` | 2.4 MB | **1.16 s** |
| 主题层：拉 `api_more_info.tgf` | `file.download` | 924 KB | **2.58 s** |
| `info` 目标 HTML（`skdfref/cvio.html`） | `file.download` | 188 KB | **1.86 s** |
| `info` 目标 HTML（`oceanref/chap8.html`） | `file.download` | 243 KB | **1.96 s** |
| 正文层候选搜索（整树文本子集） | `command.run` + `grep -r` | 0 传输 | **0.10–0.15 s** |
| 正文层候选搜索（`cpf_ref` 子目录） | `command.run` + `grep -r` | 0 传输 | 0.001 s |

正文层确实**不需要把树拉回来**：远端 `grep -r -l -m1` 直接给出候选文件路径，
再按候选逐个下载（每个 ≈1.9 s，受 `max_candidates` 限制）。

作为对照，把正文层放到**本地**扫（Windows 上的同一棵树）：

| 本地扫描方式 | 耗时 |
|---|---:|
| 旧实现纯 Python 全树扫描（`docs_search.search_docs`，实测） | 189 s |
| `rg` 对照（冷缓存 / 热缓存） | 36.8 s / ≈2 s |

即：**远端 grep ≈0.1 s，本地纯 Python ≈190 s**——差 1000 倍。
结论写进 spec：本地模式的正文层必须给 `under` 限定范围（`max_files` 兜底），
远端模式可以直接全树 grep。

## 3. 各操作的端到端成本（远端模式）

| 调用 | 取数 | 预计耗时 |
|---|---|---|
| `search(search_in="name" / "entry")` | 拉 `.fnd` 一次 | **≈1.2 s** |
| `search(search_in="topic")` | `.fnd` + `.tgf` | **≈3.8 s** |
| `search(search_in="body")`（`under=["cpf_ref"]`） | 远端 grep + 下载命中（1 个 ≈1.9 s） | **≈2 s**（每个候选 +1.9 s） |
| `info(name=...)` | `.tgf` + 1 个 HTML | **≈4.4 s** |

本地模式（`source="local"`）：全部为本地读，无传输；`search_in=name|entry` 为亚秒级。

## 4. 设计结论

1. **不预加载、不建索引**：单次 1–5 s 的成本对"查签名/查文档"这个使用节奏是可接受的，
   换来的是无状态、无陈旧索引、部署零准备；
2. 正文层实现按模式分派：远端用 `command.run` + `grep -r`（0.1 s 级），本地用纯 Python
   扫描并要求 `under`（否则 `max_files` 截断）；
3. `info` 的两步（`.tgf` + HTML）是固定成本 ≈4.4 s；如果后续要压到 1 s 级，
   可选优化是"远端 grep `.tgf` 命中行 + 只下 HTML"（省 924 KB 传输），
   本版先不做（让实现与 8123 的解析口径保持一致）；
4. 若将来接受引入状态（进程内缓存或调用方显式索引），再作为独立 spec 议题提出——
   本版明确不做（`9-skillref.md` §1 不变式 2）。

## 5. 复现命令（原始证据）

```text
# 文件计数与体积（远端）
find /opt/eda/cadence/IC618/doc -type f | wc -l              => 71319
du -sh /opt/eda/cadence/IC618/doc                            => 6.5G
find ... -iname '*.html' | wc -l                             => 8597
（html + htm + txt + xml + json + tgf）合计                    => 223.8 MB

# 正文层候选搜索（远端，整树）
cd /opt/eda/cadence/IC618/doc && grep -r -F -I -i -l -m1 \
    --include='*.html' --include='*.htm' --include='*.txt' --include='*.xml' \
    -- 'ground bounce' .                                     => ./cpf_ref/reference.html（0.10–0.15 s）

# 本地对照
python test/tb/docs_search_probe.py --root C:\Users\user\Desktop\doc --query "ground bounce"
    => 189.17 s（详见 test/tb/artifacts/skill-tooling-tb/docs-search-probe-20260921.log）
```

## 6. 附：如果**建索引**，成本与回报（旧实现 schema v3 实测）

| 项 | 实测 |
|---|---:|
| 首次建索引 + 查一次（本地树：223.8 MB 文本 / 71 319 文件） | **187.66 s**（wall 188.3 s） |
| 索引体积（`index.sqlite`） | **159.5 MB**（≈语料的 71%） |
| 第二次查询（复用索引） | **0.21 s** |
| 不建索引（本地直扫 / 远端 grep） | 189 s / **0.10–0.15 s** |

**结论**：

1. **远端模式建索引不划算**：远端 `grep -r` 整树 0.1 s，比"把 224 MB 文本拉回来 +
   建库（≥190 s + 160 MB）"便宜约三个数量级；
2. **本地模式才值**：190 s → 0.21 s，第二次查询即回本；
3. 旧实现的有效性判据只比 `schema_version` 与 `doc_root`
   （`src_bak/virtuoso_bridge/virtuoso/docs_search.py:779-788`），**不检测文档树是否变化**
   → 文档更新后索引会静默过期。要建索引必须补"文档树指纹"（文件数 + 最新 mtime 或目录摘要）。

**若将来要建，建议的顺序**：

1. 先捡便宜的：L1+L2（`.fnd` 2.4 MB + `.tgf` 924 KB ≈ 3.3 MB）做进程内缓存，
   成本≈0、可用 mtime 判新鲜（8123 的启动加载就是这个形态）；
2. L3 索引作为**可选能力**：索引路径由调用方显式给出（满足上层 §3.2
   "写到业务服务器文件，且可由请求参数确定性定位"），包负责"不存在则建、
   存在则校验指纹"，只在本地模式 + 需要多次全树 body 查询时启用。
