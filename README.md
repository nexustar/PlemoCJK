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

In `default` and `Natural`, the `hwid` (Half Widths) OpenType feature switches
those full-width ambiguous glyphs — arrows, CJK marks, block elements, box
drawing, circled / Roman numbers, ℃ ∮ … — to half-width (matching `Term`),
e.g. CSS `font-feature-settings: "hwid"`. It leaves already-half glyphs
untouched. Use it where text must line up with terminal column widths, such as
command-line output in code blocks.

In every variant, the `ss16` stylistic set makes box drawing (│ ┌ ╔ …) and
block elements (█ ▀ ░ …) join across lines at a line height of 1.6
(`line-height: 1.6` in CSS) instead of the font's own 1.25. It combines with
`hwid`: `font-feature-settings: "hwid", "ss16"`.

Natural uses a 3:5 Latin/CJK width ratio. For example, the SC family is
`PlemoCJK Natural SC`, with file `PlemoCJK-Natural-SC-Regular.ttf`.

## Webfonts

WOFF2 subsets are published to npm, one package per variant and region:
`plemocjk-sc`, `plemocjk-term-sc`, `plemocjk-natural-sc` (likewise `tc`, `jp`,
`kr`). `PlemoCJK-SC.css` covers every weight and italic; each style also
has its own stylesheet, such as `PlemoCJK-SC-Light.css`. Browsers download only
the slices a page uses.

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/plemocjk-sc@0.0.4/PlemoCJK-SC.css">
<style>
  body { font-family: "PlemoCJK SC", monospace; }
  pre  { font-feature-settings: "hwid"; }  /* half-width box drawing, arrows… */
</style>
```

Or `npm install plemocjk-sc` and `import "plemocjk-sc";`. Term and Natural use
`PlemoCJK-Term-SC.css` with family `"PlemoCJK Term SC"`, and so on. Available
weights: Thin, ExtraLight, Light, Regular, Text (450), Medium, SemiBold, Bold,
each with an Italic.

To vendor only some styles, `npx plemocjk-sc Regular Bold > PlemoCJK-SC-subset.css`
prints one stylesheet for them, laid out like the default one so it compresses
well. Put it next to a copy of the package's `SC/` directory.

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
