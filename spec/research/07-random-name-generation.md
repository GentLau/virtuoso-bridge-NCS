# HTML 随机英文名生成：方案调研与混成词算法

> 版本：v1
> 日期：2026-09-10
> 状态：调查记录（前端小功能的技术选型与算法整理），源自一次围绕「随机英文名」「monkey tomato barbecue 三词风格」「monkato 混成词风格」的逐问逐答。
> 关联：独立通用主题，与 bridge 重构无直接关系；可作为今后 Web UI / demo 页面的零件复用。

> 读者对象：有编程基础、需要在 HTML 页面里做「随机英文名」功能的工程师。不假设密码学背景，但涉及随机数质量时给出明确选型结论。
> 落地产物：[random-name-generator.html](random-name-generator.html)（本目录内，单文件、零依赖，双击即用，含三词拼接与混成词两种模式）。

---

## 0. 为什么写这份文档

需求分三个层级递进：

1. 生成随机英文名字（通用需求）；
2. `monkey tomato barbecue` 风格 —— 3 个常见英文单词随机拼接；
3. `monkato`（monkey+tomato）、`barbato`（barbecue+tomato）风格 —— 两个词的**混成词（portmanteau）**。

本文整理每级的业内做法、关键工程细节（随机源、无偏抽样、去重、长度约束）与可直接落地的算法。

---

## 1. 随机英文名：三种业内方案

按「像不像真人名」排序：

| 方案 | 原理 | 效果 | 代表实现 |
|---|---|---|---|
| **词库拼接** | 从形容词+名词+数字的现成词表随机组合 | "HappyPanda42"，不像人名但好记、无版权风险 | Docker 容器名生成器、GitHub 建议仓库名、Heroku 的 haikunator |
| **马尔可夫链/音节合成** | 用大量英文名字训练 n-gram 统计模型，按转移概率拼出新名字 | "Bradwick"、"Kaelara"——像英文名但大多查无此人 | `fantasy-name-generator`、游戏 NPC 命名 |
| **真实人口数据** | 直接用公开人口普查名单随机抽取 | 100% 像真人名 | `@faker-js/faker`（内建美/英/德/日等 locale 数据集） |

选型建议：

- **要好看、好记、不撞名**（临时标识、容器名、占位用户名）→ 词库拼接，零依赖，最轻。
- **要真实感**（测试数据、Mock 用户）→ `@faker-js/faker`，一个 CDN import 解决。
- **要幻想风**（游戏 NPC、笔名）→ 马尔可夫链方案。
- **名字要当唯一标识用** → 词库拼接 + 数字后缀 + 查重。

---

## 2. 两个关键工程细节

### 2.1 随机源用 `crypto.getRandomValues()` 而不是 `Math.random()`

- `Math.random()`：伪随机，各浏览器实现不保证均匀性，且可预测。仅用于"看着随机"的展示可以接受。
- `crypto.getRandomValues()`：Web Crypto API，密码学安全的随机数，均匀无偏。**名字用作唯一标识（临时用户名、会话 ID、占位符防碰撞）时必须用它。**

### 2.2 无偏取索引：拒绝采样

用 `x % arr.length` 有**模偏差**（数组长度不能整除 $2^{32}$ 时，靠前的元素被抽中概率略高）。业内标准做法是拒绝采样：

```javascript
function randInt(n) {                    // [0, n) 无偏
  if (n <= 1) return 0;
  const buf = new Uint32Array(1);
  const limit = Math.floor(0x100000000 / n) * n;
  do { crypto.getRandomValues(buf); } while (buf[0] >= limit);  // 拒绝超界值
  return buf[0] % n;
}
```

对几百词的词表，偏差可以忽略；但这是"对的做法"，库代码都这么写。Node 端等价物是 `crypto.randomInt(n)`。

---

## 3. 三词拼接风格：monkey tomato barbecue

本质是「常见英文单词词表 + 安全随机抽词 + 拼接」。业内现成参照：

| 参照 | 说明 |
|---|---|
| **BIP39 词表**（2048 词） | 加密货币助记词标准，最著名的精选常用词表 |
| **EFF Diceware 大词表**（7776 词） | 密码短语标准词表，专为"好记"筛选过 |
| **what3words** | 用 3 个词定位全球，就是这个风格 |
| **Docker 容器名** | 形容词+名词，同款套路，只是 2 个词 |

### 3.1 核心实现（单文件 HTML）

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Random Name Generator</title>
<style>
  body { font-family: system-ui; text-align: center; margin-top: 15vh; }
  #name { font-size: 2.5em; font-weight: bold; }
  button { font-size: 1.2em; padding: .5em 1.5em; margin-top: 1em; }
  label { display: block; margin-top: .5em; color: #555; }
</style>
</head>
<body>
  <h1 id="name">monkey tomato barbecue</h1>
  <button onclick="gen()">再来一个</button>
  <label><input type="checkbox" id="num" checked> 加数字后缀</label>

<script>
const WORDS = [
  "monkey","tomato","barbecue","apple","banana","cactus","donkey","eagle",
  "falcon","grape","hammer","island","jungle","kettle","lemon","mango",
  "needle","ocean","panda","quartz","rabbit","salmon","tiger","umbrella",
  "violin","walnut","zebra","anchor","biscuit","candle","dolphin","ember",
  "forest","garden","honey","igloo","jacket","koala","lantern","magnet",
  "napkin","otter","paddle","pepper","rocket","saddle","temple","turtle",
  "velvet","window","yogurt","bubble","coral","dragon","fossil","glacier",
  "harbor","lizard","meadow","noodle","orchid","pebble","rainbow","shelter"
];

function randInt(n) {                    // [0, n) 无偏
  if (n <= 1) return 0;
  const buf = new Uint32Array(1);
  const limit = Math.floor(0x100000000 / n) * n;
  do { crypto.getRandomValues(buf); } while (buf[0] >= limit);
  return buf[0] % n;
}

function gen() {
  const pool = [...WORDS];
  const parts = [];
  for (let i = 0; i < 3; i++) {
    parts.push(pool.splice(randInt(pool.length), 1)[0]);  // 抽走，保证同一名字内不重复
  }
  let name = parts.join(" ");
  if (document.getElementById("num").checked) {
    name += " " + randInt(1000);
  }
  document.getElementById("name").textContent = name;
}

gen();
</script>
</body>
</html>
```

### 3.2 要点

1. **词表质量决定观感**：选常见、短、易拼写的名词（BIP39/EFF 都是这么筛的），避免抽象词和专业词。
2. **同一名字内不要重复词**：`splice` 抽走比"抽 3 次拼起来"更像人起的名字。
3. **组合空间**：60 词抽 3 个不重复 = 60×59×58 ≈ 20 万种，够展示用；要当唯一 ID 就上 2048 词表或加数字。

### 3.3 可选花样

| 需求 | 改法 |
|---|---|
| 连字符 `monkey-tomato-barbecue` | `parts.join("-")` |
| 驼峰 `monkeyTomatoBarbecue` | 第二个词起首字母大写再 join |
| 词表更大 | BIP39 的 `english.txt`（2048 词）或 EFF 大词表 |
| 名字要唯一 | 数字后缀 + 本地 `Set` 查重；或 4 词暴增组合空间 |
| 服务端生成 | 同一逻辑，词表放后端；Node 用 `crypto.randomInt` |

---

## 4. 混成词风格：monkato（monkey+tomato）

这种名字叫 **portmanteau（混成词）**。用户给的例子切点规律完全一致——**前词前缀 + 后词后缀**：

| 例子 | 拆分 | 切点 |
|---|---|---|
| monkato | **monk**（monkey 前 4 字母）+ **ato**（tomato 后 3 字母） | 前词在 k=4 处切，后词在 k=3 处切 |
| barbato | **barb**（barbecue 前 4 字母）+ **ato**（tomato 后 3 字母） | 同上 |

生成混成词有**两级算法**，按优先级使用：

### 4.1 算法一：重叠合并（更自然，优先尝试）

如果前词尾巴和后词开头恰好有公共子串，直接在重叠处焊接。真实混成词如 brunch（breakfast+lunch）就是这种机制。

```
banana + anchor → bananachor（共享 "an"）
```

- 找 `a` 尾与 `b` 头的最长公共子串（≥2 字母），从大往小试；
- 命中即返回 `a + b.slice(n)`。

### 4.2 算法二：切点拼接（退回方案）

随机选两个词，各自随机选切点，前词取前缀、后词取后缀拼起来。约束：

- 前缀至少 3 字母、后缀至少 3 字母（避免 "mt" 这种残片）；
- 总长上限（≤10 字母），超长重抽；
- 拼接处出现重复字母（tig + germ → tiggerm）时去掉一个；
- 同一名字的两个源词不重复（抽走制）。

### 4.3 完整实现（单文件 HTML）

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>混成词生成器</title>
<style>
  body { font-family: system-ui; text-align: center; margin-top: 12vh; }
  #name { font-size: 3em; font-weight: bold; }
  #src  { color: #666; margin-top: .3em; }
  button { font-size: 1.2em; padding: .5em 1.6em; margin: 1.2em .3em 0; cursor: pointer; }
  #list { margin-top: 1.5em; color: #444; line-height: 1.9; }
</style>
</head>
<body>
  <div id="name">—</div>
  <div id="src"></div>
  <button onclick="genOne()">生成一个</button>
  <button onclick="genFive()">生成 5 个</button>
  <div id="list"></div>

<script>
const WORDS = [
  "monkey","tomato","barbecue","apple","banana","cactus","donkey","eagle",
  "falcon","grape","hammer","island","jungle","kettle","lemon","mango",
  "needle","ocean","panda","quartz","rabbit","salmon","tiger","umbrella",
  "violin","walnut","zebra","anchor","biscuit","candle","dolphin","ember",
  "forest","garden","honey","jacket","koala","lantern","magnet",
  "napkin","otter","paddle","pepper","rocket","saddle","temple","turtle",
  "velvet","window","yogurt","bubble","coral","dragon","fossil","glacier",
  "harbor","lizard","meadow","noodle","orchid","pebble","rainbow","shelter"
];

function randInt(n) {                    // [0, n) 无偏
  if (n <= 1) return 0;
  const buf = new Uint32Array(1);
  const limit = Math.floor(0x100000000 / n) * n;
  do { crypto.getRandomValues(buf); } while (buf[0] >= limit);
  return buf[0] % n;
}
const pick = arr => arr[randInt(arr.length)];

function blend(a, b) {
  // 1) 重叠合并：找 a 尾与 b 头最长公共子串（≥2 字母）
  const maxN = Math.min(a.length, b.length) - 1;
  for (let n = maxN; n >= 2; n--) {
    if (a.endsWith(b.slice(0, n))) return a + b.slice(n);
  }
  // 2) 切点拼接：前缀≥3，后缀≥3
  let k1 = 3 + randInt(a.length - 3);            // monkey: 3~5 → "mon"~"monke"
  let k2 = 2 + randInt(Math.max(1, b.length - 4)); // tomato: 2~3 → "mato"/"ato"
  let p = a.slice(0, k1), s = b.slice(k2);
  if (p[p.length - 1] === s[0]) p = p.slice(0, -1);  // 去重复字母
  return p + s;
}

function makeOne() {                       // 抽两个不同词，控制总长
  for (let i = 0; i < 10; i++) {
    const a = pick(WORDS), b = pick(WORDS);
    if (a === b) continue;
    const name = blend(a, b);
    if (name.length <= 10) return { name, a, b };
  }
  const a = pick(WORDS), b = pick(WORDS);
  return { name: blend(a, b), a, b };
}

function genOne() {
  const { name, a, b } = makeOne();
  document.getElementById("name").textContent = name;
  document.getElementById("src").textContent = `${a} × ${b}`;
  document.getElementById("list").innerHTML = "";
}

function genFive() {
  const el = document.getElementById("list");
  el.innerHTML = "";
  for (let i = 0; i < 5; i++) {
    const { name, a, b } = makeOne();
    const div = document.createElement("div");
    div.textContent = `${name}  ←  ${a} + ${b}`;
    el.appendChild(div);
  }
}

genOne();
</script>
</body>
</html>
```

### 4.4 更讲究的进阶（可选）

| 技巧 | 效果 | 说明 |
|---|---|---|
| **音节边界切分** | 更像真词 | 按"辅音簇+元音簇"切块再拼（mon-key → mon + ma-to → monmato 偏规则），比瞎切中点自然，但要写元音检测 |
| **词尾词根表** | monkato / -land / -berry | 备一份常见词尾（ato, land, berry, city...），固定后半段、随机前半段，风格更统一 |
| **加权重叠** | 提高焊接率 | 给"字母对匹配"打分，找 a 尾/b 头最相似处合并，重叠概率大增 |
| **n-gram 再校验** | 过滤怪词 | 用英文 n-gram 频率表给生成结果打分，扔掉不像词的组合 |

---

## 5. 结论

1. 展示用途、好玩好记：**词库拼接**（三词风格）或**重叠合并 + 切点拼接**（混成词风格）已完全够用，几十行、零依赖、单文件 HTML。
2. 名字当标识符：必须 `crypto.getRandomValues()` + 拒绝采样，词表至少几百词或加数字后缀。
3. 真实感优先：`@faker-js/faker` CDN import，人口数据直接抽。
4. 混成词算法优先级：**先试重叠合并（自然），失败再切点拼接（保底）**；约束 = 前缀/后缀最短 3 字母 + 总长上限 + 去拼接处重复字母 + 源词不重复。
