# PlemoCJK

***Ple***x ***Mo***no ***CJK*** -- 把 [PlemolJP](https://github.com/yuru7/PlemolJP) 扩展到简中 / 繁中 / 日文 / 韩文四个地区的等宽编程字体。

**[English](README.md)**

---

PlemoCJK 是 PlemolJP 的 fork。上游把 IBM Plex Mono 和 IBM Plex Sans **JP** 合成为
日文编程字体；PlemoCJK 把覆盖面扩展到 **简体中文、繁体中文、日文、韩文**，
做法是出四个分地区子字体，再打包成一个 TTC。

英数字侧沿用上游的处理（Hack 合并、引号放大、箭头调整、ttfautohint），
ASCII 部分的观感与 PlemolJP 一致。

四个地区子字体（SC / TC / JP / KR），每个把 IBM Plex Mono 和对应地区的
IBM Plex Sans 合成。

三个变体：

| 变体 | 半角 / 全角（px） | 符号¹ | 箭头 / 记号² | 全角空格 | Nerd Fonts |
|---|:---:|:---:|:---:|:---:|:---:|
| **default** | 528 / 1056 | 半角 | 全角 | 空白 | - |
| **Term** | 600 / 1200 | 半角 | 半角 | 可视化 | 半角 |
| **Natural** | 600 / 1000 | 半角 | 全角 | 空白 | - |

¹ 拉丁-1 符号（§ ° ± × ÷）、数学运算符（∑ ∫ ≠ √ ∞）、希腊 / 西里尔（α Ω、А я）、
引号（“ ” ‘ ’）为半角。
² 箭头（← → ⇒）、几何图形（■ ● ★）、圈号 / 罗马数字（① Ⅰ）和 CJK 标点（… ※ №）
在 `default` 和 `Natural` 里保持全角；`Term` 把所有歧义宽度字形都做成半角以适配终端网格。

Natural 使用西文与 CJK 字宽 3:5 的比例。例如简中字体族名为
`PlemoCJK Natural SC`，文件名为 `PlemoCJK-Natural-SC-Regular.ttf`。

## 构建

```bash
# 1. 取源字体（SC/TC/KR 下载 + SHA-256 校验，JP 用仓库里的）
python3 fetch_sources.py

# 2. 构建（上游的镜像里有 fontforge / ttfautohint）
docker run --rm -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder

# 快速验证：只出 Term Regular 一个文件
docker run --rm -e DEBUG=1 -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder

# 3. 打成 TTC
npm install
node --max-old-space-size=8192 bundle_ttc.mjs

# 4. 检查
python3 check_fonts.py --variant default --ttc build/ttc/PlemoCJK-Regular.ttc

# 5. 打包
./release.sh
```

`make.sh` 的环境变量：`REGIONS="SC KR"`、`VARIANTS="Term"`、
`SKIP_PREPARE=1`、`DEBUG=1`、`MAX_PARALLEL=4`。
