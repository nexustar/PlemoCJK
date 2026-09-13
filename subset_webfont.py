#!/usr/bin/env python3
"""Split PlemoCJK region fonts into Google-Fonts-style woff2 webfont subsets.

Usage:
    python3 subset_webfont.py [BUILD_DIR]

Reads the default-variant Regular TTF for each region from BUILD_DIR
(default: build/) and produces:

    BUILD_DIR/release/PlemoCJK_webfont_VERSION/
        SC/
            PlemoCJKSC-Regular.NNN.woff2
            PlemoCJKSC-Regular.css
        TC/ ...
        JP/ ...
        KR/ ...

The unicode-range slice definitions come from the Google Fonts CSS API
(Noto Sans SC/TC/JP/KR), which splits ~17k CJK codepoints into ~120
frequency-ordered subsets.  Results are cached in .webfont_cache/.

Requires: fonttools, brotli  (pip install fonttools brotli)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from configparser import ConfigParser
from pathlib import Path

REGION_TO_GOOGLE_FONT = {
    "SC": "Noto+Sans+SC",
    "TC": "Noto+Sans+TC",
    "JP": "Noto+Sans+JP",
    "KR": "Noto+Sans+KR",
}

CACHE_DIR = Path(__file__).parent / ".webfont_cache"

BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_google_css(font_name: str) -> str:
    url = f"https://fonts.googleapis.com/css2?family={font_name}&display=swap"
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_unicode_ranges(css: str) -> list[str]:
    return re.findall(r"unicode-range:\s*([^;]+);", css)


def load_slices(region: str) -> list[str]:
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{region}.json"

    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    google_name = REGION_TO_GOOGLE_FONT[region]
    print(f"  Fetching Google Fonts CSS for {google_name} ...")
    css = fetch_google_css(google_name)
    ranges = parse_unicode_ranges(css)
    if not ranges:
        raise RuntimeError(f"No unicode-range found for {google_name}")

    with open(cache_file, "w") as f:
        json.dump(ranges, f)
    print(f"  Cached {len(ranges)} slices for {region}")
    return ranges


def subset_font(input_ttf: str, output_woff2: str, unicode_range: str) -> bool:
    cmd = [
        "pyftsubset",
        input_ttf,
        f"--unicodes={unicode_range}",
        "--flavor=woff2",
        f"--output-file={output_woff2}",
        "--layout-features=*",
        "--glyph-names",
        "--no-hinting",
        "--desubroutinize",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        return False
    out = Path(output_woff2)
    if out.exists() and out.stat().st_size == 0:
        out.unlink()
        return False
    return out.exists()


def read_ini() -> dict[str, str]:
    config = ConfigParser()
    config.read(Path(__file__).parent / "build.ini")
    return dict(config["DEFAULT"])


def find_input_font(build_dir: Path, font_name: str, region: str) -> Path | None:
    candidates = [
        f"{font_name}-{region}-Regular.ttf",
        f"{font_name}{region}-Regular.ttf",
    ]
    for name in candidates:
        ttf = build_dir / name
        if ttf.exists():
            return ttf
    for name in candidates:
        for p in build_dir.rglob(name):
            return p
    return None


def generate_css(
    family_name: str,
    slices: list[tuple[int, str, str]],
) -> str:
    rules = []
    for idx, urange, filename in slices:
        rules.append(
            f"/* {idx} */\n"
            f"@font-face {{\n"
            f"  font-family: '{family_name}';\n"
            f"  font-style: normal;\n"
            f"  font-weight: 400;\n"
            f"  font-display: swap;\n"
            f"  src: url('{filename}') format('woff2');\n"
            f"  unicode-range: {urange};\n"
            f"}}"
        )
    return "\n\n".join(rules) + "\n"


def process_region(
    region: str,
    input_ttf: Path,
    output_dir: Path,
    font_name: str,
):
    print(f"\n### {region}: {input_ttf.name} ###")
    slices = load_slices(region)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = input_ttf.stem
    css_slices: list[tuple[int, str, str]] = []
    skipped = 0

    for idx, urange in enumerate(slices, 1):
        woff2_name = f"{base_name}.{idx}.woff2"
        woff2_path = output_dir / woff2_name

        if subset_font(str(input_ttf), str(woff2_path), urange):
            css_slices.append((idx, urange, woff2_name))
        else:
            skipped += 1

    family = f"{font_name}{region}"
    css_content = generate_css(family, css_slices)
    (output_dir / f"{base_name}.css").write_text(css_content)

    total_kb = sum((output_dir / n).stat().st_size for _, _, n in css_slices) / 1024
    print(f"  {len(css_slices)} slices, {skipped} skipped, total {total_kb:.0f} KB")


def main():
    ini = read_ini()
    font_name = ini.get("font_name", "PlemoCJK")
    version = ini.get("version", "dev")
    build_dir = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(ini.get("build_fonts_dir", "build"))
    )

    if not build_dir.exists():
        print(f"ERROR: {build_dir} not found", file=sys.stderr)
        sys.exit(1)

    canonical = font_name.replace(" ", "")
    webfont_dir = build_dir / "release" / f"{canonical}_webfont_{version}"
    print(f"Output: {webfont_dir}")

    processed = 0
    for region in REGION_TO_GOOGLE_FONT:
        ttf = find_input_font(build_dir, canonical, region)
        if ttf is None:
            print(f"WARNING: {canonical}-{region}-Regular.ttf not found, skipping")
            continue
        process_region(region, ttf, webfont_dir / region, font_name)
        processed += 1

    if processed == 0:
        print("ERROR: no input fonts found", file=sys.stderr)
        sys.exit(1)

    print(f"\n### Done: {webfont_dir} ###")


if __name__ == "__main__":
    main()
