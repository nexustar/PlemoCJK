# PlemoCJK webfonts

Default variant, Regular (400, upright), for SC / TC / JP / KR.
This orphan branch contains generated WOFF2 subsets and their CSS.

```html
<link rel="stylesheet" href="./SC/PlemoCJK-SC-Regular.css">
<style>
  pre, code { font-family: 'PlemoCJK SC', monospace; }
</style>
```

Serve this directory over HTTP(S), preserving the relative paths. Replace SC
with TC, JP, or KR to select regional glyph shapes. Each CSS uses a distinct
family (`PlemoCJK SC`, `PlemoCJK TC`, `PlemoCJK JP`, `PlemoCJK KR`). Only Regular
is included; browsers may synthesize bold and italic.

## Provenance

Rebuilt locally from source commit
`d5cfed9fd0c1140cee9cbac5280ad8a8cdf8ca29`, the same revision as
[Action run 35382951246](https://github.com/nexustar/PlemoCJK/actions/runs/35382951246).
The Action TTF artifacts were not reused because downloading them required
GitHub authentication. IBM source Regular TTFs were checked against `sources.lock`.
Build selection: `STYLES=Regular REGIONS="SC TC JP KR" VARIANTS=default`.

WOFF2 subsets use fontTools 4.63.0 and Brotli, preserve layout features, and
omit hinting. Frequency slices follow the source checkout's cached Google
Fonts ranges; additional slices retain every remaining source codepoint,
including regional fallback coverage. CSS ranges are disjoint and match each
subset's actual cmap. Every generated WOFF2 was reopened and its character
coverage and Regular metadata verified. `manifest.json` records source TTF
hashes, output hashes, sizes, and Unicode ranges.

## License

Fonts are distributed under SIL Open Font License 1.1; see `LICENSE` and
`licenses/` for the upstream license notices.
