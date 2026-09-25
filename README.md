# PlemoCJK

***Ple***x ***Mo***no ***CJK*** -- a monospaced programming font that extends
[PlemolJP](https://github.com/yuru7/PlemolJP) from Japanese to
Simplified Chinese / Traditional Chinese / Japanese / Korean.

**[中文说明](README-zh.md)**

Each of the four regional subfonts (SC / TC / JP / KR) pairs IBM Plex Mono
with that region's IBM Plex Sans. The four are also bundled into one TTC per
variant and weight.

Three variants:

| Variant | Half / full width (units, 1000/em) | Symbols¹ | Arrows / marks² | Full-width space | Nerd Fonts |
|---|:---:|:---:|:---:|:---:|:---:|
| **default** | 528 / 1056 | half | full | blank | - |
| **Term** | 600 / 1200 | half | half | visible | half |
| **Natural** | 600 / 1000 | half | full | blank | - |

¹ Latin-1 symbols (§ ° ± × ÷), math operators (∑ ∫ ≠ √ ∞), Greek / Cyrillic
(α Ω, А я) and quotes (“ ” ‘ ’) are half-width.
² Arrows (← → ⇒), geometric shapes (■ ● ★), circled / Roman numerals (① Ⅰ)
and marks such as … ※ № stay full-width in `default` and `Natural`; `Term`
makes every ambiguous-width glyph half-width for terminal grids.

Natural uses a 3:5 Latin/CJK width ratio. For example, the SC family is
`PlemoCJK Natural SC`, with file `PlemoCJK-Natural-SC-Regular.ttf`.

## Webfonts

Each release publishes WOFF2 subsets of the default variant to the
`webfonts` branch, served by GitHub Pages. One stylesheet per region covers
every weight and italic; browsers download only the slices a page uses.

```html
<link rel="stylesheet" href="https://nexustar.github.io/PlemoCJK/PlemoCJK-SC.css">
<style>code, pre { font-family: "PlemoCJK SC", monospace; }</style>
```

Replace `SC` with `TC`, `JP` or `KR` for other regions.

## Building

```bash
# 1. Fetch source fonts (SC/TC/KR download + SHA-256 verification; JP is in the repo)
python3 fetch_sources.py

# 1b. Regenerate SC Text at weight 450 from the IBM master (needs ~3 GB memory)
pip install "fontmake[pathops]"
python3 regen_sc_text.py

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

See [HOW_TO_BUILD.md](./HOW_TO_BUILD.md) for details, including webfonts and
`make.sh` options.

Based on [PlemolJP](https://github.com/yuru7/PlemolJP) v3.1.0.
