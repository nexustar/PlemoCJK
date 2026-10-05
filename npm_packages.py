#!/usr/bin/env python3
"""Build one npm package per region from a subset_webfont.py output directory.

Usage: python3 npm_packages.py WEBFONT_DIR OUT_DIR
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from plemocjk_config import VARIANTS, hyphenate_tag

REGIONS = {
    "SC": "Simplified Chinese",
    "TC": "Traditional Chinese",
    "JP": "Japanese",
    "KR": "Korean",
}
REPOSITORY = "nexustar/PlemoCJK"
# Shipped as each package's `bin`: merges chosen styles into one stylesheet.
CLI = "webfont_css.mjs"


def link_or_copy(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def readme(name: str, region: str, family: str, css: str, version: str, styles: list[str]) -> str:
    return f"""# {name}

[{family}](https://github.com/{REPOSITORY}) webfont for {REGIONS[region]}:
a monospaced programming font pairing IBM Plex Mono with IBM Plex Sans {region}.
WOFF2 files are split into slices; browsers load only those a page uses.

```js
// Every weight and italic
import "{name}";
// Or a single style
import "{name}/{css}-Light.css";
```

To vendor a few styles as one stylesheet, laid out like the default one so it
compresses well:

```sh
npx {name} Regular Bold Light > {css}-subset.css
```

Keep it next to a copy of `{region}/`; only the chosen styles' slices are needed.

Or from a CDN:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/{name}@{version}/{css}.css">
```

```css
code, pre {{ font-family: "{family}", monospace; }}
```

Styles: {", ".join(styles)}.

Licensed under the SIL Open Font License 1.1; see `LICENSE` and `licenses/`.
"""


def build_package(src: Path, out: Path, region: str, manifest: dict, font_name: str) -> Path:
    canonical = font_name.replace(" ", "")
    variant = manifest.get("variant", "default")
    tag = hyphenate_tag(VARIANTS[variant].tag(region))
    family = VARIANTS[variant].family_name(font_name, region)
    name = f"{canonical.lower()}-{tag.lower()}"
    version = manifest["version"].removeprefix("v")
    fonts = manifest["regions"][region]
    styles = [Path(entry["css"]).stem.rsplit("-", 1)[1] for entry in fonts]
    default_css = f"{canonical}-{tag}.css"

    pkg = out / name
    if pkg.exists():
        shutil.rmtree(pkg)
    (pkg / tag).mkdir(parents=True)
    for css in [default_css] + [entry["css"] for entry in fonts]:
        shutil.copy2(src / css, pkg / css)
    for entry in fonts:
        for item in entry["files"]:
            link_or_copy(src / item["file"], pkg / item["file"])
    shutil.copy2(Path(__file__).parent / CLI, pkg / "cli.mjs")
    shutil.copy2(src / "LICENSE", pkg / "LICENSE")
    shutil.copytree(src / "licenses", pkg / "licenses")
    (pkg / "README.md").write_text(
        readme(name, region, family, f"{canonical}-{tag}", version, styles), encoding="utf-8"
    )
    package = {
        "name": name,
        "version": version,
        "description": f"{family} webfont: monospaced programming font for {REGIONS[region]}",
        "keywords": ["font", "webfont", "woff2", "monospace", "programming", "cjk", REGIONS[region].lower()],
        "homepage": f"https://github.com/{REPOSITORY}",
        "repository": {"type": "git", "url": f"git+https://github.com/{REPOSITORY}.git"},
        "license": "OFL-1.1",
        "main": default_css,
        "style": default_css,
        "bin": {name: "cli.mjs"},
        "exports": {
            ".": f"./{default_css}",
            "./*.css": "./*.css",
            "./package.json": "./package.json",
        },
        "sideEffects": ["*.css"],
        "files": ["*.css", "cli.mjs", f"{tag}/", "licenses/"],
    }
    (pkg / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    return pkg


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    manifest = json.loads((src / "manifest.json").read_text())
    for region in manifest["regions"]:
        pkg = build_package(src, out, region, manifest, "PlemoCJK")
        print(pkg)


if __name__ == "__main__":
    main()
