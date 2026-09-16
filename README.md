# PlemoCJK

***Ple***x ***Mo***no ***CJK*** -- a monospaced programming font that extends
[PlemolJP](https://github.com/yuru7/PlemolJP) from Japanese to
Simplified Chinese / Traditional Chinese / Japanese / Korean.

**[中文说明](README-zh.md)**

Four regional subfonts (SC / TC / JP / KR), each pairing IBM Plex Mono with
that region's IBM Plex Sans.

Two variants:

| Variant | Half / full (px) | Symbols¹ | Arrows / marks² | Full-width space | Nerd Fonts |
|---|:---:|:---:|:---:|:---:|:---:|
| **default** | 540 / 1080 | half | full | blank | - |
| **Term** | 600 / 1200 | half | half | visible | half |

¹ Latin-1 symbols (§ ° ± × ÷), math operators (∑ ∫ ≠ √ ∞), Greek / Cyrillic
(α Ω, А я) and quotes (“ ” ‘ ’) are half-width.
² Arrows (← → ⇒), geometry (■ ● ★), circled / Roman numbers (① Ⅰ) and CJK
punctuation (… ※ №) stay full-width in `default`; `Term` makes every ambiguous
glyph half-width for terminal grids.

## Building

```bash
# 1. Fetch source fonts (SC/TC/KR download + SHA-256 verification; JP is in the repo)
python3 fetch_sources.py

# 2. Build (the upstream image has fontforge / ttfautohint)
docker run --rm -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder

# Quick smoke test: produce only Term Regular for one region
docker run --rm -e DEBUG=1 -v "$(pwd):/work" ghcr.io/yuru7/composite-font-builder

# 3. Bundle into TTC
npm install
node --max-old-space-size=8192 bundle_ttc.mjs

# 4. Check
python3 check_fonts.py --variant default --ttc build/ttc/PlemoCJK-Regular.ttc

# 5. Package
./release.sh
```

See [HOW_TO_BUILD.md](./HOW_TO_BUILD.md) for details.

Based on [PlemolJP](https://github.com/yuru7/PlemolJP) v3.1.0.
