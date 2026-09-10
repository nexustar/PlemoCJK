# PlemoCJK 设计与实现（第一里程碑）

PlemoCJK 是 [yuru7/PlemolJP](https://github.com/yuru7/PlemolJP) 的 fork，把上游的
「IBM Plex Mono + IBM Plex Sans JP」扩展成覆盖简体中文、繁体中文、日文、韩文的
四个分地区子字体，并提供一个 TTC 打包。本文记录第一里程碑已经定下的设计决策。

本里程碑建立在上游 v3.1.0（commit `02492b7`）之上。

---

## 1. 分地区子字体

四个子字体，每个 = Plex Mono（英数字侧，上游已有的处理）+ 本地区 IBM Plex Sans
+ 回退补入 + 谚文。

| 子字体 | 家族名 | CJK 侧主源 |
|---|---|---|
| SC | `PlemoCJK SC` | IBM Plex Sans SC |
| TC | `PlemoCJK TC` | IBM Plex Sans TC |
| JP | `PlemoCJK JP` | IBM Plex Sans JP |
| KR | `PlemoCJK KR` | IBM Plex Sans KR |

### 命名规则

沿用上游的拼接规则，地区修饰子插在 `35` 之后、`Console` 之前：

```
家族名 = PlemoCJK[35] <REGION>[ Console][ NF][ HS]
文件名 / PostScript 名 = 去掉所有空格
```

| 变体 | 家族名（SC） | 文件名 |
|---|---|---|
| 默认 | `PlemoCJK SC` | `PlemoCJKSC-Regular.ttf` |
| Console | `PlemoCJK SC Console` | `PlemoCJKSCConsole-Regular.ttf` |
| ConsoleNF | `PlemoCJK SC Console NF` | `PlemoCJKSCConsoleNF-Regular.ttf` |
| 35 | `PlemoCJK35 SC` | `PlemoCJK35SC-Regular.ttf` |
| 35Console | `PlemoCJK35 SC Console` | `PlemoCJK35SCConsole-Regular.ttf` |

TTC 文件名不含地区（四个地区都在里面）：`PlemoCJKConsole-Regular.ttc`。

### 字重与斜体

与上游一致：8 个字重（Thin / ExtraLight / Light / Regular / Text / Medium /
SemiBold / Bold）× 正斜体 = 16 个样式。IBM Plex Sans 各语言版都没有斜体，
CJK 侧斜体由上游的 9 度 skew 生成（`ITALIC_ANGLE = 9`）。

### 构建矩阵

第一批只出三个变体：默认、`Console`、`ConsoleNF`。
`35` 与 `HS` 系列的代码路径保留，由 `build.ini` 的 `[build]` 段控制：

```ini
DEFAULT_VARIANTS = default, Console, ConsoleNF
FULL_VARIANTS = default, 35, Console, 35Console, ConsoleNF, 35ConsoleNF,
    HS, 35HS, ConsoleHS, 35ConsoleHS
```

`make.sh` 用 `VARIANT_SET=full` 切换到全量，或用 `VARIANTS="..."` 直接指定。

---

## 2. 回退补入（fallback fill）

只补本地区缺失的码位，**绝不覆盖已有字形**。补入顺序来自 Adobe Source Han Sans
`region-map` 的实际决策（地区间的字形接近程度）：

```
SC ← JP ← TC ← KR
TC ← SC ← JP ← KR
JP ← SC ← TC ← KR
KR ← JP ← SC ← TC
```

每条链末尾的 KR 主要负责把谚文带进去。其直接结果是：**四个子字体的码位集合完全一致**，
等于四个源字体码位的并集。这一点很关键，见 §7。

实测（Regular，IBM/plex commit `bf26009`）：

| 地区 | 自有码位 | 补入 | 来源 |
|---|---|---|---|
| SC | 29,286 | 19,454 | JP 1,637 / TC 6,386 / KR 11,431 |
| TC | 23,646 | 25,094 | SC 12,121 / JP 1,542 / KR 11,431 |
| JP | 15,718 | 33,022 | SC 15,205 / TC 6,386 / KR 11,431 |
| KR | 12,182 | 36,558 | JP 14,985 / SC 15,187 / TC 6,386 |

合并后每个子字体 48,740 码位，加上 CJK 兼容汉字别名（§2.3）共 49,468 码位。

`python3 prepare_cjk.py --report` 输出这张表。

### 2.1 不做跨地区 locl

汉字部分不加 `locl`。分地区出字体就是为了避免 locl 方案在不同排版引擎下
行为不一致。回退补入的字形来自别的地区，合并时丢掉补入源的 GSUB/GPOS，
只保留主地区字体的 GSUB（上游本来就在 FontForge 阶段删 GPOS）。

### 2.2 排除的码位

`U+274C CROSS MARK`：上游故意从英数字侧删掉它，好让系统的 emoji 字体接管。
只有 Plex KR 有这个字形，所以从补入目标和 KR 主源的 cmap 里都去掉，
保持四个地区一致。配置项 `EXCLUDE_CODEPOINTS`。

### 2.3 CJK 兼容汉字别名

IBM Plex Sans 四个语言版都没有 `U+F900–FAFF`（CJK 兼容汉字）。这会让
KS X 1001 缺 246 字、GBK 缺 3 字。这些码位在 Unicode 里是统合汉字的
**正规等价**（singleton decomposition，只是读音不同的同字），所以
`prepare_cjk.py` 给它们建 cmap 别名指向对应的统合汉字字形，不新增任何轮廓。
728 个码位因此补齐，KS X 1001 与 GBK 覆盖变成零缺失。配置项
`ALIAS_COMPAT_IDEOGRAPHS`。

### 2.4 cmap 去别名（injective cmap）

`prepare_cjk.py` 最后会保证 cmap 是单射的：一个字形只被一个码位引用，
多出来的码位各自持有一份字形副本。

原因：上游 `fontforge_script.py` 的 `delete_duplicate_glyphs` /
`materialize_altuni_glyphs` 处理 altuni 时有漏洞——当别名组里有一个码位
也被英数字侧提供时，共享字形会被整个 `clear()`，另一个码位跟着消失。
实测 Plex TC 的 4,909 组 Big5/HKSCS 别名里有若干与 Powerline 的 PUA
（`U+E0A0–E0D4`）撞上，导致 TC 子字体丢掉 35 个码位，其中包括 `启`、
`全角波浪号 U+FF5E`、`U+2609` 等常用字符。

让 cmap 单射之后 altuni 根本不产生，这类问题从原理上消失。代价是每个
子字体多 2,700–5,700 个字形槽；字形字节完全相同，所以不影响 TTC 的 glyf 共享。

### 2.5 GSUB feature 裁剪

只保留 `build.ini` 的 `GSUB_KEEP_FEATURES`：

```
ccmp, locl, liga, calt, rlig, salt, case,
ss01..ss04, zero, ordn, frac, afrc, numr, dnom, sups, subs, sinf
```

丢掉的有两类，都有明确理由：

- **宽度变体**（`pwid` / `hwid` / `fwid` / `twid` / `qwid`）和**纵排**
  （`vert` / `vrt2`）：在等幅字体里一旦被应用就会破坏等宽；上游也已经删掉
  `vhea` / `vmtx`，纵排本来就不支持。
- **异体字**（`jp78` / `jp83` / `jp90` / `hojo` / `nlck` / `expt` / `trad` /
  `ruby` / `nalt` / `ital` / `hkna` / `vkna` / `pkna` / `aalt` / `dlig`）：
  IBM Plex Sans JP 单这一部分就有约 5,800 个只能通过 GSUB 访问的字形。
  不裁剪的话 Nerd Fonts 版（+10,522 字形）会超过 65,535 的上限。

这是相对上游 PlemolJP 的一处行为改变，见 README 的「与上游的差异」。

### 2.6 拉丁字形清除的修正

上游 `delete_duplicate_glyphs` 把 `U+00C0–U+0259` 的拉丁字形无条件从 CJK 侧
`clear()`，意图是统一用 IBM Plex Mono 的字形。但 Plex Mono 没有
`U+0193`、`U+01C2`、`U+01F5`、`U+01F8`、`U+01F9`、`U+0250–U+0258` 这些
IPA / 扩展拉丁字母，清除之后两边都没有，实测 JIS X 0213 缺 14 字、GBK 缺 1 字
（`U+0251 ɑ`）。

PlemoCJK 改成先收集英数字侧实际拥有的码位（含 altuni），只在英数字侧确实有的
情况下才清除 CJK 侧。保留下来的字形按 `set_width_600_or_1000` 的规则变成全角，
与上游对 `U+00D7` / `U+00F7` 的处理一致。

---

## 3. 谚文

谚文相关码位（`HANGUL_RANGES`）全部放进四个子字体，全部来自 IBM Plex Sans KR：

```
1100-11FF, 302E-302F, 3130-318F, 3200-321E, 3260-327F,
A960-A97F, AC00-D7A3, D7B0-D7FB, FFA0-FFDC
```

Plex KR 实际有 11,329 个（11,172 个音节 + 兼容字母 + 带圈/带括号韩文）。

**宽度**：Plex KR 的谚文音节宽 892（不是 1000）。上游
`set_width_600_or_1000` 的「`500 < 宽 < 1000` → 居中放进 1000 宽」分支
正好处理了这一点，无需特殊代码。四个子字体走同一段代码，因此输出的谚文
字形**逐字节相同**，TTC 的 glyf 共享才成立。

**半角谚文字母** `U+FFA1–FFDC` 按半角处理，从全角归一化里排除
（`HALF_WIDTH_HANGUL_RANGES`）。Plex KR 当前没有这些字形，这条规则是为了
将来源字体补上时不会被错误地全角化。

---

## 4. 英数字侧只生成一次

英数字侧（Plex Mono 经 FontForge 处理并由 ttfautohint 加 hint 的
`*-eng-hinted.ttf`）与地区无关，每个（变体, 样式）只生成一次，四个地区
复用同一个文件，字节相同。

实现：`fontforge_script.py` 增加两个开关。

- `--eng-only`：只写英数字侧，文件名不含地区
  （`fontforge_PlemoCJKConsole-Regular-eng.ttf`）。
- `--region XX`：只写 CJK 侧（`fontforge_PlemoCJKSCConsole-Regular-jp.ttf`）。
  英数字侧仍然在内存里构建（CJK 侧的宽度变换需要它），但不写出。

`make.sh` 分两段：先对每个变体跑一次 `--eng-only` + ttfautohint，
再并行跑「地区 × 变体」。

这里有一个前提：非 Console 变体的 `merge_hack` 会按 CJK 侧的覆盖范围决定
删掉哪些 Hack 字形，也就是说英数字侧的结果依赖 CJK 侧的码位集合。
因为四个地区的码位集合完全一致（§2），这个依赖不会造成地区间差异。

---

## 5. 元数据

每个子字体由 `plemocjk_metadata.py` 统一设置：

| 项目 | 内容 |
|---|---|
| `meta` dlng / slng | SC→`Hans`、TC→`Hant`、JP→`Jpan`、KR→`Kore` |
| OS/2 `ulCodePageRange` | bit 0（1252）+ SC:18(936) / TC:20(950) / JP:17(932) / KR:19(949)+21(1361) |
| `fsSelection` | 置 `USE_TYPO_METRICS`（bit 7） |
| `name` 本地化家族名 | zh_CN / zh_TW / ja / ko 各一个，把家族名里的地区记号换成本地语言标签 |
| `hdmx` | 只给 1:2 变体生成 |

`name` 的英文名沿用上游的规则（Regular/Italic/Bold/BoldItalic 四个基本样式
不写 nameID 16/17，其余写）。

### hdmx

奇数 ppem 11–47（19 条记录）：

```
hdmx[ppem][glyph] = cell_count * ceil(ppem / 2)
cell_count = round(advance / HALF_WIDTH_12)   # HALF_WIDTH_12 = 528
```

半角 = `ceil(ppem/2)`，全角 = 2 × 半角，连字 = n × 半角。同时
`head.flags |= 0x0010`（instructions may depend on point size）。

3:5 变体**不生成** hdmx：`5 × 半角px == 3 × 全角px` 对任意 ppem 没有整数解。

---

## 6. 源字体获取

`fetch_sources.py` 从 IBM/plex 的固定 commit 下载 **unhinted** TTF：

```
https://raw.githubusercontent.com/IBM/plex/<PLEX_COMMIT>/packages/
  plex-sans-{sc,tc,jp,kr}/fonts/complete/ttf/unhinted/IBMPlexSans{SC,TC,JP,KR}-{Weight}.ttf
```

当前固定在 `bf260093582f04622aacc1e9f9ca604d7ccd0c42`（master）。
SHA-256 记录在 `sources.lock`（32 个文件），首次运行时生成，之后每次校验。
换 commit 要用 `--update-lock` 重新生成。

IBM 发布的 npm 包只有 woff/woff2，不能用。

SC / TC / KR 放在 `source/IBM-Plex-Sans-{SC,TC,KR}/unhinted/`，已加入
`.gitignore`（不入库）。JP 沿用上游已经提交进仓库的那份——实测它与固定
commit 的 unhinted JP **哈希完全一致**，所以 `sources.lock` 是自洽的。

### 6.1 SC 的 Text 从母版重新生成

IBM 发布的 Plex Sans SC，Text 实例的插值位置是 **425**，而 JP / TC 是 **450**，
于是四个地区并排时只有 SC 的 Text 偏细约 5%（实测表见 §9）。
`regen_sc_text.py` 只重做这一个字重，其余七个字重仍用发布件。

1. 从 GitHub API `repos/IBM/plex/releases?per_page=100` 找出 tag 形如
   `@ibm/plex-sans-sc@X.Y.Z` 的最新 release，取附件 `sources.zip`
   （当前是 `@ibm/plex-sans-sc@1.1.0`，186,169,692 字节）。URL 与 SHA-256 记在
   `sources.lock` 的 `sc_master_source` 键下，以后每次运行都校验；zip 缓存在
   `source/ibm-plex-sans-sc-sources.zip`（已 `.gitignore`）。
   zip 里也有 `instances/{postscript,truetype}/` 下的预插值实例，
   但那些仍然是 425，不能用。
2. 只解出 `sources/masters/IBM Plex Sans SC.glyphs`（210 MB，Glyphs 2 格式）。
3. 按括号配对扫描 `instances` 数组，定位 `name = Text` 的那一块，把它的
   `interpolationWeight = 425;` 改成 `450`。**不做全局替换**：母版里 Medium 写着
   505、SemiBold 写着 602，都是与发布件不符的过期值，既不能动也不能参照。
   实测补丁只改 2 个字节，文件长度不变。（`instanceInterpolations` 是 Glyphs
   自己缓存的权重系数，glyphsLib 只把它当 lib 键搬运、不参与插值，所以不用改。）
4. `fontmake -g <file> -i "IBM Plex Sans SC Text" -o ttf
   --overlaps-backend pathops --no-production-names`。约 5 分钟、峰值 3 GB 内存
   （解析 210 MB 的母版本身约 2.5 分钟）；glyphsLib 会警告 kern class 缺失，无害。
   master / instance UFO 等中间产物放在 `TMPDIR` 下，跑完即删。
5. 与 IBM 发布件的 SC Text 对齐：
   - **cmap**：fontmake 会多出 `U+0302` / `U+0303` / `U+24C7`（IBM 没有映射），
     删掉；IBM 把 `U+22EF` 也指向 `U+2026` 的字形而 fontmake 没做，补上。
     补的时候不靠字形名（发布件用 production names，这里用
     `--no-production-names`，有一部分名字不同），而是用「发布件里指向同一字形的
     另一个码位」在再生成字体里对应的字形。结果 SC 八个字重 cmap 完全一致。
   - **name**：nameID < 256 全部取发布件的（家族名 / 样式名 / 版本 / 唯一 ID /
     本地化名）。≥ 256 保留再生成字体自己的，因为 GSUB 的 FeatureParams
     （stylistic set 的显示名）会引用它们。
   - **OS/2 / hhea / post / head**：`usWeightClass = 450`，并把 panose、
     `sTypo*` / `usWin*` / `sxHeight` / `sCapHeight`、hhea 的升降部、
     下划线位置、`fontRevision` 等对齐到发布件，让输出可以直接当发布件的
     替换件用。其余表交给后段流程（上游 `fontforge_script.py` /
     `fonttools_script.py` 本来就会重写）。
6. 输出 `source/regenerated/IBMPlexSansSC-Text.ttf`（已 `.gitignore`）。

`build.ini` 用两个显式开关接上：

```ini
REGENERATED_FONT = regenerated/IBMPlexSans{region}-{style}.ttf
REGENERATED_STYLES = SC:Text
```

`plemocjk_config.Config.region_source_path()` 据此在发布件和再生成件之间选，
`prepare_cjk.py` 找不到再生成件时报错并提示先跑 `regen_sc_text.py`。
把 `REGENERATED_STYLES` 清空就回到「全部用发布件」。

**流程忠实性**：同一套步骤不改 `interpolationWeight`（Regular 的 360）生成
Regular，得到的「一」68 /「丨」70 与 IBM 发布件逐值一致，说明 425 → 450 是
唯一的变量。

CI 里这一步是独立的 `regen-sc-text` job：`pip install fontmake[pathops]` →
`fetch_sources.py --regions SC` → `regen_sc_text.py` → `regen_sc_text.py --check`，
用 `actions/cache` 缓存 `source/ibm-plex-sans-sc-sources.zip` 与
`source/regenerated/`（key 含 `sources.lock` 与 `regen_sc_text.py` 的哈希），
结果作为 `regenerated-sc-text` 产物交给 `prepare`。

### 关于「unhinted」

IBM 的 unhinted 包并不是完全没有指令：JP 有 456 个字形带共 23 KB 指令，
KR 有 202 个并且带 `fpgm`/`prep`/`cvt`，SC/TC 才是真正干净的。
`prepare_cjk.py` 默认丢掉所有 TrueType 指令（`--keep-hints` 可关闭），原因：

1. hinting 由后段的 ttfautohint 只加在英数字侧（与上游一致）；
2. KR 的指令依赖它自己的 `fpgm`，搬到别的地区会坏；
3. 丢掉之后四个地区的谚文字形字节完全一致，TTC 共享才成立。

---

## 7. TTC 打包

每个（变体, 样式）把四个地区子字体用 `otb-ttc-bundle -x`
（npm 包 `otb-ttc-bundle`，版本锁在 `package.json`）打成一个
`PlemoCJK{Variant}-{Style}.ttc`。

`-x`（sparse glyph sharing）按字形内容哈希跨子字体统一字形，建一条全局
字形序列，每个子字体的 `loca` 取其单调子序列，拼出一份 `glyf`。
fontTools 的 `TTCollection.save(shareTables=True)` 只按整表去重，做不到这件事。

前置条件（破坏任一条共享率就会塌）：

- TrueType 轮廓
- 四个子字体 UPM 相同（都是 1000）
- 同一个字形必须得到同一串字节（谚文、英数字侧都满足）

内存：`ot-builder` 处理 4 × 5 万字形要几 GB，所以 `bundle_ttc.mjs` 和
`package.json` 的 npm script 都带 `--max-old-space-size=8192`。

实测（Regular，本机 podman 里跑上游镜像构建）：

| TTC | 输入 4 个 TTF | TTC | 压缩比 | glyf 共享 |
|---|---|---|---|---|
| `PlemoCJKConsole-Regular.ttc` | 55.4 MB | 22.4 MB | 2.47× | 202,301 槽 → 84,339 块（58.3%） |
| `PlemoCJKConsoleNF-Regular.ttc` | 62.7 MB | 24.8 MB | 2.53× | 234,493 槽 → 92,265 块（60.7%） |

TTC 表副本数（4 个子字体）：`glyf` 1 份，`fpgm`/`cvt`/`prep`/`gasp` 各 1 份
（英数字侧四地区字节相同，直接验证了 §4 的复用），
`loca`/`cmap`/`hmtx`/`name`/`meta`/`post`/`GSUB` 各 4 份，`GPOS` 3 份。
打包耗时约 50 秒/个。

---

## 8. 检查与 CI

`check_fonts.py`：

1. 每个子字体的字形数与距 65,535 的余量
2. 四个地区 cmap 码位集合完全一致
3. JIS X 0208 / JIS X 0213 / GB 2312 / GBK / Big5 / KS X 1001 覆盖
   （字符集从 Python 内置 codec 推导，不需要外部数据文件）
4. 谚文码位数、音节数、宽度
5. 中 / 日 / 韩 / 混排测试句无 `.notdef`
6. 元数据（meta、代码页、`USE_TYPO_METRICS`、hdmx 的 1:2 比例、本地化名）
7. 「一」「丨」笔画粗细在八个字重上四个地区一致，**没有例外**。
   实测最大偏差 3.0%（ExtraLight 的「丨」32 对 33，差 1 个单位），
   所以容差从 8% 收紧到 5%。原来唯一的例外（SC Text）已由 §6.1 解决。
8. TTC 里 `glyf` 只有一份、子字体数与顺序、各子字体 cmap 一致

`regen_sc_text.py --check` 另外单独验证再生成的 SC Text：
「一」「丨」与 JP / TC 的 Text 逐值相同，且 cmap 与 SC Regular 完全一致。

`.github/workflows/build.yml` 四段：

```
regen-sc-text  IBM 母版 -> interpolationWeight 450 -> fontmake -> 上传 SC Text (带缓存)
prepare        下载+校验源字体 -> prepare_cjk.py -> 上传 prepared 产物
build          矩阵 (4 地区 x N 变体)，在 ghcr.io/yuru7/composite-font-builder 容器里跑 make.sh
bundle         汇总全部 TTF -> bundle_ttc.mjs -> check_fonts.py -> release.sh -> 上传 zip
```

`regen-sc-text` 单独一段是因为它要装 fontmake、下 186 MB 的母版 zip、
跑 5 分钟 3 GB 内存的插值，而结果只有 9 MB 且只依赖 `sources.lock`，
适合缓存。`prepare` 单独一段是因为 12 个构建 job 没必要各自重做同样的地区合成；
`bundle` 单独一段是因为 TTC 打包内存需求高，且必须等四个地区都齐。

`bundle` 里的 `release.sh` 跑在 runner 宿主机上而不是容器里，因为它需要
`zip` / `unzip`，而 `composite-font-builder` 镜像没有这两个命令
（`ubuntu-latest` 有；workflow 里仍然先确认一次，必要时 `apt-get install`）。

构建 job 不用 `container:` 而是在 `ubuntu-latest` 上 `docker run`，因为
`ghcr.io/yuru7/composite-font-builder` 镜像里没有 `git` 也没有 `node`，
`actions/checkout` 和 `upload-artifact` 在容器 job 里会走降级路径。
这样也和 `HOW_TO_BUILD.md` 文档里的调用方式保持一致。

可优化项（本里程碑未做）：`prepared-cjk` 产物是 8 字重 × 4 地区约 400 MB，
会被 12 个构建 job 各下载一次。按地区拆成 4 个产物可以把传输量降到 1/4。

---

## 9. 已解决：SC Text 字重偏细

IBM 发布的 Plex Sans SC 的 Text 插值位置是 425，JP / TC 是 450，结果 SC Text
比其他地区细约 5%。**已通过从母版按 450 重新生成解决**（方法见 §6.1）。

实测「一」的横画高度与「丨」的竖画宽度（IBM Plex Sans unhinted，
KR 无汉字故不参与）：

| 字重 | 一 SC/TC/JP | 丨 SC/TC/JP | 偏差 |
|---|---|---|---|
| Thin | 20 / 20 / 20 | 20 / 20 / 20 | 0% |
| ExtraLight | 32 / 32 / 32 | 33 / 33 / 32 | 3.0% |
| Light | 52 / 52 / 52 | 54 / 54 / 54 | 0% |
| Regular | 68 / 68 / 68 | 70 / 70 / 70 | 0% |
| Text（IBM 发布件，425） | **80** / 84 / 84 | **84** / 89 / 89 | **4.8% / 5.6%** |
| **Text（本项目再生成，450）** | **84** / 84 / 84 | **89** / 89 / 89 | **0%** |
| Medium | 100 / 100 / 100 | 105 / 105 / 105 | 0% |
| SemiBold | 116 / 116 / 116 | 125 / 125 / 125 | 0% |
| Bold | 132 / 132 / 132 | 142 / 142 / 142 | 0% |

剩下的最大偏差是 ExtraLight 的「丨」（32 对 33，3.0%，1 个单位的取整差），
所以 `check_fonts.py` 的容差可以从 8% 收紧到 5%，并且不再需要任何例外。

---

## 10. 已知差异与未做的事

- **JIS X 0213 缺 2 字**：`U+2985` / `U+2986`（白括号）在四个 Plex Sans 里
  都没有，需要自己画。这是四个标准里唯一剩下的缺口。
- **GSUB 异体字被裁掉**：见 §2.5，相对上游 PlemolJP 是行为改变。
- **没有做 CJK 侧 hinting**：与上游一致，只有英数字侧过 ttfautohint。
  Sarasa Gothic 用 Chlorophytum 给汉字/假名/谚文加 hint，是后续里程碑的事。
- **标点宽度规则**没有按 Sarasa 的方案重做，仍是上游 PlemolJP 的逐字符调整。
- **35 / HS 变体**代码路径保留但默认不构建。
