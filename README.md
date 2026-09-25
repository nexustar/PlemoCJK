# PlemoCJK webfonts v0.0.3

Default variant for SC / TC / JP / KR. `PlemoCJK-SC.css` holds Regular,
Bold and their italics; `PlemoCJK-SC-Light.css` and the like hold one
style each. Browsers load only the slices a page uses.

```html
<link rel="stylesheet" href="PlemoCJK-SC.css">
<link rel="stylesheet" href="PlemoCJK-SC-Light.css">
<style>code, pre { font-family: 'PlemoCJK SC', monospace; }</style>
```

Replace SC with TC, JP or KR for regional glyph forms. `manifest.json`
lists source TTF and WOFF2 hashes. Fonts are licensed under the SIL Open
Font License 1.1; see `LICENSE` and `licenses/`.
