#!/usr/bin/env python3
"""Generate default-variant WOFF2 subsets and per-region CSS for all built styles.

Usage: python3 subset_webfont.py [BUILD_DIR] (default: build)
Requires fonttools and brotli. Google ranges are cached in .webfont_cache/.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import urllib.request
from configparser import ConfigParser
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

from plemocjk_config import ALL_STYLES

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


def parse_codepoints(unicode_range: str) -> set[int]:
    points = set()
    for item in unicode_range.split(","):
        bounds = item.strip().upper().removeprefix("U+").split("-")
        start = int(bounds[0].replace("?", "0"), 16)
        end = int(bounds[-1].replace("?", "F"), 16)
        if len(bounds) > 2 or not 0 <= start <= end <= 0x10FFFF:
            raise ValueError(f"Invalid Unicode range: {item}")
        points.update(range(start, end + 1))
    return points


def format_codepoints(points: set[int]) -> str:
    runs = []
    for cp in sorted(points):
        if runs and cp == runs[-1][1] + 1:
            runs[-1][1] = cp
        else:
            runs.append([cp, cp])
    return ", ".join(
        f"U+{a:X}" if a == b else f"U+{a:X}-{b:X}" for a, b in runs
    )


def plan_slices(points: set[int], ranges: list[str]) -> list[set[int]]:
    """Resolve overlaps as CSS does, then retain all remaining source characters."""
    remaining = set(points)
    groups = []
    # CSS checks overlapping rules last-first; keep Latin together.
    for value in reversed(ranges):
        group = parse_codepoints(value) & remaining
        if group:
            groups.append(group)
            remaining -= group
    groups.reverse()
    extra = sorted(remaining)
    groups.extend(set(extra[i:i + 256]) for i in range(0, len(extra), 256))
    return groups


def subset_font(input_ttf: Path, output_woff2: Path, points: set[int]) -> None:
    options = subset.Options()
    options.layout_features = ["*"]
    options.glyph_names = True
    options.hinting = False
    options.desubroutinize = True
    with TTFont(input_ttf, recalcTimestamp=False) as font:
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=points)
        subsetter.subset(font)
        # Layout closure can retain aliases outside the requested range.
        for table in font["cmap"].tables:
            if table.isUnicode() and hasattr(table, "cmap"):
                table.cmap = {cp: name for cp, name in table.cmap.items() if cp in points}
        font.flavor = "woff2"
        font.save(output_woff2)
    with TTFont(output_woff2) as check:
        if set(check.getBestCmap() or {}) != points:
            raise RuntimeError(f"Subset coverage mismatch: {output_woff2}")


def read_ini() -> dict[str, str]:
    config = ConfigParser()
    config.read(Path(__file__).parent / "build.ini")
    return dict(config["DEFAULT"])


def find_input_font(build_dir: Path, font_name: str, region: str, style: str) -> Path | None:
    candidates = [
        f"{font_name}-{region}-{style}.ttf",
        f"{font_name}{region}-{style}.ttf",
    ]
    for name in candidates:
        ttf = build_dir / name
        if ttf.exists():
            return ttf
    for name in candidates:
        for p in build_dir.rglob(name):
            return p
    return None


def find_inputs(build_dir: Path, font_name: str) -> dict[str, list[Path]]:
    inputs = {region: [] for region in REGION_TO_GOOGLE_FONT}
    for style in ALL_STYLES:
        fonts = {r: find_input_font(build_dir, font_name, r, style) for r in inputs}
        if not any(fonts.values()):
            continue
        missing = [r for r, path in fonts.items() if path is None]
        if missing:
            raise SystemExit(f"ERROR: missing {style} input fonts: {', '.join(missing)}")
        for region, path in fonts.items():
            inputs[region].append(path)
    if not any(inputs.values()):
        raise SystemExit("ERROR: no default-variant input fonts found")
    return inputs


def generate_css(
    family_name: str,
    slices: list[tuple[int, str, str]],
    weight: int,
    style: str,
) -> str:
    rules = []
    for idx, urange, filename in slices:
        rules.append(
            f"/* {idx} */\n"
            f"@font-face {{\n"
            f"  font-family: '{family_name}';\n"
            f"  font-style: {style};\n"
            f"  font-weight: {weight};\n"
            f"  font-display: swap;\n"
            f"  src: url('{filename}') format('woff2');\n"
            f"  unicode-range: {urange};\n"
            f"}}"
        )
    return "\n\n".join(rules) + "\n"


def process_region(
    region: str,
    input_ttfs: list[Path],
    output_dir: Path,
    font_name: str,
):
    ranges = load_slices(region)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    canonical = font_name.replace(" ", "")
    css_name = f"{canonical}-{region}.css"
    rules = []
    expected = set()

    # Publish only after every style succeeds.
    with tempfile.TemporaryDirectory(prefix=f".{region}-", dir=output_dir.parent) as tmp:
        staging = Path(tmp)
        for input_ttf in input_ttfs:
            with TTFont(input_ttf) as font:
                points = set(font.getBestCmap() or {})
                weight = font["OS/2"].usWeightClass
                style = "italic" if font["OS/2"].fsSelection & 1 else "normal"
            if not points:
                raise RuntimeError(f"No Unicode cmap: {input_ttf}")
            groups = plan_slices(points, ranges)
            css_slices = []
            for idx, group in enumerate(groups, 1):
                name = f"{input_ttf.stem}.{idx}.woff2"
                subset_font(input_ttf, staging / name, group)
                expected.add(name)
                css_slices.append((idx, format_codepoints(group), name))
            rules.append(generate_css(f"{font_name} {region}", css_slices, weight, style))
            print(f"  {input_ttf.name}: {len(groups)} slices, {len(points)} codepoints")
        (staging / css_name).write_text("\n".join(rules), encoding="utf-8")
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in staging.glob("*.woff2"):
            path.replace(output_dir / path.name)
        (staging / css_name).replace(output_dir / css_name)
        for old_style in ALL_STYLES:
            for stem in (f"{canonical}-{region}-{old_style}", f"{canonical}{region}-{old_style}"):
                for path in output_dir.glob(f"{stem}.*.woff2"):
                    if path.name not in expected:
                        path.unlink()
                (output_dir / f"{stem}.css").unlink(missing_ok=True)


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

    inputs = find_inputs(build_dir, canonical)
    for region, ttfs in inputs.items():
        process_region(region, ttfs, webfont_dir / region, font_name)

    print(f"\n### Done: {webfont_dir} ###")


if __name__ == "__main__":
    main()
