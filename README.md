# PlemoCJK

***Ple***x ***Mo***no ***CJK*** — 把 [PlemolJP](https://github.com/yuru7/PlemolJP) 扩展到简中 / 繁中 / 日文 / 韩文四个地区的等宽编程字体。

**→ [PlemoCJK 章节](#plemocjk-分地区-cjk-编程字体) ｜ [设计文档](docs/PlemoCJK-plan.md)**

---

以下是上游 PlemolJP 的 README，PlemoCJK 继承其全部处理（全角空格可视化、
Console / 35 幅 / Nerd Fonts 变体、8 字重 × 正斜体等）。

# PlemolJP (プレモル ジェイピー)

***Ple***x ***Mo***no ***L***anguage ***JP***

IBM Plex Mono と IBM Plex Sans JP を合成した日本語プログラミングフォント PlemolJP (プレモル ジェイピー)

**ダウンロードはこちら ➡ [Releases](https://github.com/yuru7/PlemolJP/releases/latest)**

> 💡 [Homebrew (Mac) でのインストール方法](doc/install_via_homebrew.md)

![image](https://github.com/yuru7/PlemolJP/raw/images/beer.jpg)

PlemolJP では合成元の [IBM Plex Mono](https://github.com/IBM/plex) シリーズと同様に、ノーマル・イタリックの両スタイルに対応しました。また、各スタイルごとに8種のウェイト (Thin~Bold) をご用意しています。  

さらに日本語環境でのプログラミングでつまずきがちな全角スペースの誤入力に気づけるよう、全角スペースを可視化する修正を加えています。  

> 💡 全角スペースの可視化が不要な場合は、リリースの Assets より `PlemolJP_HS_vx.x.x.zip` の名前形式になっている zip ファイルを選択してください。(HS: Hidden Space)

> 💡 Powerline 記号等が含まれる Nerd Fonts 対応版は、リリースの Assets より `PlemolJP_NF_vx.x.x.zip` の名前形式になっている zip ファイルを選択してください。(NF: Nerd Fonts)

|**フォント ファミリー**|**説明**|
|:------------:|:---|
|**PlemolJP**|文字幅比率「半角1:全角2」の通常版の PlemolJP。主にASCIIコードの英数字記号に IBM Plex Mono の字体を使い、その他の日本語文字や記号類に IBM Plex Sans JP を使っている。|
|**PlemolJP Console**|IBM Plex Mono の字体を除外せずに全て適用したフォントファミリー。矢印記号などの多くの記号が半角で表示されるため、コンソールでの利用や記号類は可能な限り半角で表示したい人にオススメ。|
|**PlemolJP35**|通常版の PlemolJP の文字幅比率を「半角3:全角5」にしたフォントファミリー。英数字が通常版の PlemolJP よりも大きく表示される。日本語が少ない文書やコードの場合にはこちらの方が読みやすいと感じるかもしれない。|
|**PlemolJP35 Console**|PlemolJP Console の文字幅比率を 半角3:全角5 にしたフォントファミリー|

> 💡 その他、公開中のプログラミングフォント
> - 日本語文字に源柔ゴシック、英数字部分に Hack を使った [**白源 (はくげん／HackGen)**](https://github.com/yuru7/HackGen)
> - 日本語文字に源真ゴシック、英数字部分に Fira Mono を使った [**Firge (ファージ)**](https://github.com/yuru7/Firge)
> - 日本語文字にBIZ UDゴシック、英数字部分に JetBrains Mono を使った [**UDEV Gothic**](https://github.com/yuru7/udev-gothic)

|Thin|ExtraLight|Light|Regular|
|:---:|:---:|:---:|:---:|
|![Thin](https://user-images.githubusercontent.com/13458509/133928702-21f1f391-e83a-4825-9059-36cf3d35f6f7.png)|![ExtraLight](https://user-images.githubusercontent.com/13458509/133928717-f5e17c66-b4e1-47fe-950f-ca3bc574a874.png)|![Light](https://user-images.githubusercontent.com/13458509/133928734-3ca98395-97b9-417b-96a1-ef83f614739a.png)|![Regular](https://user-images.githubusercontent.com/13458509/133928745-fe85ba2e-0d5e-406c-9d23-c832e11bc7b4.png)|

|Text|Medium|SemiBold|Bold|
|:---:|:---:|:---:|:---:|
|![Text](https://user-images.githubusercontent.com/13458509/133928757-af5b6b82-5e1f-41bb-a925-f03769bdad00.png)|![Medium](https://user-images.githubusercontent.com/13458509/133928766-a4b22651-cc1c-48d7-b729-15a6a4070f44.png)|![SemiBold](https://user-images.githubusercontent.com/13458509/133928774-d8467d02-c301-4bef-84e5-1702f9f9645d.png)|![Bold](https://user-images.githubusercontent.com/13458509/133928784-7cc5f571-1161-41de-81b8-b97573e3f524.png)|

## ビルド

[HOW_TO_BUILD.md](./HOW_TO_BUILD.md) 参考

---

# PlemoCJK 分地区 CJK 编程字体

PlemoCJK 是 PlemolJP 的 fork。上游把 IBM Plex Mono 和 IBM Plex Sans **JP** 合成为
日文编程字体；PlemoCJK 把覆盖面扩展到 **简体中文、繁体中文、日文、韩文**，
做法是出四个分地区子字体，再打包成一个 TTC。

英数字侧完全沿用上游的处理（含 Hack 合并、引号放大、箭头调整、全角空格可视化、
ttfautohint），所以 ASCII 部分的观感与 PlemolJP 一致。

## 四个子字体

| 子字体 | 家族名 | 汉字 / 字形取向 |
|---|---|---|
| **SC** | `PlemoCJK SC` | 简体中文（IBM Plex Sans SC） |
| **TC** | `PlemoCJK TC` | 繁体中文（IBM Plex Sans TC） |
| **JP** | `PlemoCJK JP` | 日文（IBM Plex Sans JP，= 上游 PlemolJP 的取向） |
| **KR** | `PlemoCJK KR` | 韩文（IBM Plex Sans KR） |

变体命名沿用上游规则，地区记号插在 `35` 之后、`Console` 之前：
`PlemoCJK SC`、`PlemoCJK SC Console`、`PlemoCJK SC Console NF`、
`PlemoCJK35 SC Console`。文件名与 PostScript 名去掉空格
（`PlemoCJKSCConsoleNF-Regular.ttf`）。

第一批发布三个变体：默认、`Console`、`ConsoleNF`。
`35` 幅与 `HS`（全角空格不可视化）的代码路径保留，用
`VARIANT_SET=full` 开启。

字重与样式与上游相同：8 字重 × 正斜体 = 16 个样式。

## 为什么分地区而不是用 locl

同一个码位在中日韩的标准字形不同（例如 `直`、`骨`、`次`）。常见方案有两种：
一个字体里塞四套字形 + 用 `locl` 按语言切换，或者分地区出字体。

PlemoCJK 选后者，原因：四地区合一大约需要 73,900 个字形，超过 TrueType
65,535 的上限约 8,400 个；而且 `locl` 依赖排版引擎正确传语言标签，
终端和编辑器里经常传不对。

## 回退补入规则

单个地区的 Plex Sans 覆盖并不完整——例如 Plex SC 缺 21 个 JIS X 0208 常用字
（見貝車長門風飛馬魚龍等）、缺全部半角片假名；Plex JP 缺 2,238 个 GB 2312 字；
Plex KR 一个汉字都没有。

所以每个子字体都会用别的地区补齐缺失码位，**只补缺的，绝不覆盖已有字形**：

```
SC ← JP ← TC ← KR
TC ← SC ← JP ← KR
JP ← SC ← TC ← KR
KR ← JP ← SC ← TC
```

顺序取自 Adobe Source Han Sans 的 `region-map`（地区间字形接近程度）。
结果是四个子字体的码位集合**完全一致**，只是汉字取向不同。

一个直接后果：**KR 子字体的汉字字形来自日文**（Plex Sans KR 一个汉字都没有，
链首是 JP）。韩国的汉字字形传统上确实接近日本的旧字体，这是四个可选来源里最合适的。
补齐后的覆盖：

| 标准 | 缺失 |
|---|---|
| JIS X 0208 | 0 |
| JIS X 0213 | 2（`U+2985` / `U+2986` 白括号，四个 Plex Sans 都没有） |
| GB 2312 | 0 |
| GBK | 0 |
| Big5 | 0 |
| KS X 1001 | 0 |

汉字部分**不加 `locl`**；补入字形来自别的地区时，丢掉来源的 GSUB/GPOS，
只保留主地区字体的 GSUB。

## 谚文

谚文（`U+AC00–D7A3` 等共 11,329 个码位）放进**全部四个**子字体，都来自
IBM Plex Sans KR。Plex KR 的谚文音节宽 892，会被居中放进 1000 宽的全角格；
四个子字体走同一段代码，输出字形逐字节相同，这是 TTC 能共享 `glyf` 的前提。

半角谚文字母 `U+FFA1–FFDC` 按半角处理，不归一到全角。

## 一个文件：TTC

每个（变体, 样式）的四个地区子字体用
[`otb-ttc-bundle -x`](https://www.npmjs.com/package/otb-ttc-bundle)
打成一个 TTC：

```
build/ttc/PlemoCJKConsole-Regular.ttc   # 里面有 SC / TC / JP / KR 四个子字体
```

`-x` 按字形内容哈希跨子字体共享 `glyf`，所以一个 TTC 比四个 TTF 小得多。
安装后在字体菜单里能看到四个家族，按需要选地区即可。

每个子字体带 `meta` 表的 `dlng`/`slng`（`Hans`/`Hant`/`Jpan`/`Kore`）、
对应地区的 OS/2 代码页位、以及 zh_CN / zh_TW / ja / ko 的本地化家族名，
方便系统和应用自动挑到合适的那个。

## 已知差异

- **SC 的 Text 字重偏细约 5%**：IBM 发布的 Plex Sans SC，Text 的插值位置是 425，
  JP / TC 是 450。这是上游源字体的差异，本里程碑不处理。
- **JIS X 0213 缺 2 字**：`U+2985` / `U+2986`。
- **裁掉了部分 GSUB 异体字**：为了让 Nerd Fonts 版（+10,522 字形）留在
  65,535 字形以内，丢掉了宽度变体（`pwid`/`hwid`/`fwid`/`twid`/`qwid`）、
  纵排（`vert`/`vrt2`）和 Plex Sans JP 的异体字（`jp78`/`jp83`/`hojo`/
  `nlck`/`ruby`/`nalt` 等，约 5,800 字形）。前两类在等宽字体里被应用反而
  会破坏等宽，所以这个取舍同时也是修正。这是相对上游 PlemolJP 的行为改变。
- **CJK 侧没有 hinting**：与上游一致，只有英数字侧过 ttfautohint。

顺带修掉的一个上游问题：上游把 `U+00C0–U+0259` 的拉丁字形无条件从 CJK 侧删掉
（意在统一用 Plex Mono 的字形），但 Plex Mono 并没有 `U+0250–U+0258` 这些 IPA 字母，
结果两边都没有，JIS X 0213 缺 14 字、GBK 缺 1 字。PlemoCJK 改成「只在英数字侧确实
有这个码位时才删」。

## 与上游的关系

PlemoCJK fork 自 PlemolJP v3.1.0（commit `02492b7`），对上游文件的改动刻意保持最小，
方便以后继续合并上游更新：

| 文件 | 改动 |
|---|---|
| `build.ini` | 新增 `[regions]` / `[region.XX]` / `[build]` 三段 |
| `fontforge_script.py` | 加 `--region` / `--eng-only` 两个开关、半角谚文例外、拉丁字形清除改为条件判断，约 70 行 |
| `fonttools_script.py` | 加地区参数、英数字侧复用、`--eng-hint` 模式，约 50 行 |
| `make.sh` | 地区循环 + 变体开关（重写） |
| `release.sh` | 按地区打包（重写） |

新增文件：`fetch_sources.py`、`prepare_cjk.py`、`plemocjk_config.py`、
`plemocjk_metadata.py`、`check_fonts.py`、`bundle_ttc.mjs`、`sources.lock`。
`PlemolJP` 原有的 `JP_FONT` 路径在不带 `--region` 时仍然可用。

## 构建

```bash
# 1. 取源字体（SC/TC/KR 下载 + SHA-256 校验，JP 用仓库里的）
python3 fetch_sources.py

# 2. 构建（上游的镜像里有 fontforge / ttfautohint）
docker run --rm -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder

# 快速验证：只出 Console Regular 一个文件
docker run --rm -e DEBUG=1 -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder

# 3. 打成 TTC
npm install
node --max-old-space-size=8192 bundle_ttc.mjs

# 4. 检查
python3 check_fonts.py --variant Console --ttc build/ttc/PlemoCJKConsole-Regular.ttc

# 5. 打包
./release.sh
```

`make.sh` 的环境变量：`REGIONS="SC KR"`、`VARIANTS="Console"`、
`VARIANT_SET=full`、`SKIP_PREPARE=1`、`DEBUG=1`、`MAX_PARALLEL=4`。

---

## PlemoCJK (English summary)

PlemoCJK is a fork of [PlemolJP](https://github.com/yuru7/PlemolJP) that extends
it from Japanese to **four region subfonts: SC, TC, JP, KR**. Each subfont pairs
IBM Plex Mono (the ASCII side, processed exactly as upstream does) with that
region's IBM Plex Sans.

- **Fallback fill.** Each region's missing codepoints are filled from the other
  regions in Source-Han-Sans-derived order (`SC ← JP ← TC ← KR`, etc.), never
  overwriting an existing glyph. All four subfonts end up with an identical
  codepoint set (49,468) and zero gaps in JIS X 0208, GB 2312, GBK, Big5 and
  KS X 1001.
- **No cross-region `locl`.** Four-regions-in-one would need ~73,900 glyphs,
  about 8,400 over the 65,535 limit, and `locl` relies on applications passing
  correct language tags — terminals usually don't.
- **Hangul in all four subfonts**, from IBM Plex Sans KR, centred from its
  native 892 advance into the 1000-unit full-width cell. Halfwidth hangul
  letters (`U+FFA1–FFDC`) stay halfwidth.
- **One file.** `otb-ttc-bundle -x` packs the four subfonts of each
  (variant, style) into a single `.ttc` with a shared `glyf` table.
- **Known issues.** IBM's SC Text weight is ~5% lighter than JP/TC; `U+2985`
  and `U+2986` are absent from all four Plex Sans fonts; width-variant,
  vertical and Japanese itaiji GSUB features are dropped to fit the Nerd Fonts
  build under 65,535 glyphs.

See [docs/PlemoCJK-plan.md](docs/PlemoCJK-plan.md) for the full design.

## PlemoCJK (日本語の概要)

PlemoCJK は [PlemolJP](https://github.com/yuru7/PlemolJP) のフォークで、
日本語だけだった対応範囲を **簡体字中国語 / 繁体字中国語 / 日本語 / 韓国語の
4 地域サブフォント** に広げたものです。英数字側は上流の処理をそのまま使うので、
ASCII 部分の見た目は PlemolJP と変わりません。

- **回退補入**: 各地域の IBM Plex Sans に無いコードポイントだけを他地域から補う
  (`SC ← JP ← TC ← KR` など、Source Han Sans の region-map に基づく順序)。
  既存グリフは上書きしない。結果として 4 サブフォントのコードポイント集合は完全に一致し、
  JIS X 0208 / JIS X 0213 (2 字を除く) / GB 2312 / GBK / Big5 / KS X 1001 を網羅する。
- **漢字に locl は使わない**: 4 地域を 1 フォントに入れると約 73,900 グリフ必要で
  65,535 の上限を約 8,400 超える。また locl はアプリが言語タグを正しく渡す前提で、
  ターミナルでは期待できない。
- **ハングルは 4 サブフォント全部に入れる**: IBM Plex Sans KR 由来。
  KR のハングルは幅 892 なので、1000 幅の全角枠に中央寄せされる。
  半角ハングル字母 (`U+FFA1–FFDC`) は半角のまま。
- **1 ファイル配布**: `otb-ttc-bundle -x` で 4 サブフォントを 1 つの `.ttc` にまとめ、
  `glyf` を共有する。
- **既知の差異**: IBM 版 Plex Sans SC の Text は JP/TC より約 5% 細い。
  `U+2985` / `U+2986` は 4 つの Plex Sans すべてに無い。
  Nerd Fonts 版を 65,535 グリフ以内に収めるため、幅バリアント・縦組み・
  日本語異体字の GSUB feature を落としている。

詳細は [docs/PlemoCJK-plan.md](docs/PlemoCJK-plan.md) を参照。
