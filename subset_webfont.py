#!/usr/bin/env python3
"""Generate per-region WOFF2 subsets and CSS for each built variant.

Usage: python3 subset_webfont.py [BUILD_DIR] [--variant NAME ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import Executor, ProcessPoolExecutor, as_completed, wait
from configparser import ConfigParser
from pathlib import Path

from fontTools import subset
from fontTools import version as fonttools_version
from fontTools.ttLib import TTFont

from plemocjk_config import ALL_STYLES, VARIANTS, hyphenate_tag

REGION_TO_GOOGLE_FONT = {
    "SC": "Noto+Sans+SC",
    "TC": "Noto+Sans+TC",
    "JP": "Noto+Sans+JP",
    "KR": "Noto+Sans+KR",
}

CACHE_DIR = Path(__file__).parent / ".webfont_cache"

PRINTABLE_ASCII = set(range(0x20, 0x7F))

# Styles in the regional default CSS; every style also gets its own CSS.
DEFAULT_CSS_STYLES = ("Regular", "Bold", "Italic", "BoldItalic")

# Source fonts of the default variant (no Nerd Fonts).
LICENSES = {
    "source/LICENSE_IBM-Plex": "LICENSE_IBM-Plex",
    "source/hack/LICENSE": "LICENSE_Hack",
}

BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_google_css(font_name: str) -> str:
    url = f"https://fonts.googleapis.com/css2?family={font_name}"
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


def plan_slices(
    points: set[int], ranges: list[str], universe: set[int] | None = None
) -> list[tuple[set[int], str]]:
    """Split POINTS into (codepoints, unicode-range) slices, in CSS order.

    Overlapping Google ranges resolve as CSS does (last rule wins), keeping
    Latin together. Characters outside them go into 256-codepoint slices
    placed first, so each can use a single span: later rules win wherever a
    span overlaps a Google slice.

    Boundaries are drawn on UNIVERSE (default POINTS) so that styles with
    different coverage share them; slices without POINTS come back empty.
    """
    remaining = set(points if universe is None else universe)
    groups = []
    for value in reversed(ranges):
        group = parse_codepoints(value) & remaining
        if group:
            groups.append(group & points)
            remaining -= group
    groups.reverse()
    extra = sorted(remaining)
    spans = [set(extra[i:i + 256]) & points for i in range(0, len(extra), 256)]
    return [
        (s, format_codepoints(set(range(min(s), max(s) + 1)))) if s else (s, "")
        for s in spans
    ] + [(g, format_codepoints(g)) for g in groups]


def subset_font(input_ttf: Path, output_woff2: Path, points: set[int]) -> None:
    options = subset.Options()
    options.layout_features = ["*"]
    options.hinting = False
    options.drop_tables += ["meta"]
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


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent,
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def read_ini() -> dict[str, str]:
    config = ConfigParser()
    config.read(Path(__file__).parent / "build.ini")
    return dict(config["DEFAULT"])


def file_tag(variant: str, region: str) -> str:
    """Output tag of a variant/region pair, e.g. 'SC' or 'Term-SC'."""
    return hyphenate_tag(VARIANTS[variant].tag(region))


def find_input_font(
    build_dir: Path, font_name: str, region: str, style: str, variant: str = "default"
) -> Path | None:
    tag = file_tag(variant, region)
    candidates = [
        f"{font_name}-{tag}-{style}.ttf",
        f"{font_name}{tag.replace('-', '')}-{style}.ttf",
    ]
    for name in candidates:
        ttf = build_dir / name
        if ttf.exists():
            return ttf
    for name in candidates:
        for p in build_dir.rglob(name):
            return p
    return None


def find_inputs(build_dir: Path, font_name: str, variant: str = "default") -> dict[str, list[Path]]:
    """Input fonts per region for VARIANT; empty when none are built."""
    inputs = {region: [] for region in REGION_TO_GOOGLE_FONT}
    for style in ALL_STYLES:
        fonts = {r: find_input_font(build_dir, font_name, r, style, variant) for r in inputs}
        if not any(fonts.values()):
            continue
        missing = [r for r, path in fonts.items() if path is None]
        if missing:
            raise SystemExit(f"ERROR: missing {variant} {style} input fonts: {', '.join(missing)}")
        for region, path in fonts.items():
            inputs[region].append(path)
    return inputs if any(inputs.values()) else {}


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
            f"  src: url('{filename}') format('woff2');\n"
            f"  unicode-range: {urange};\n"
            f"}}"
        )
    return "\n\n".join(rules) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def process_region(
    region: str,
    input_ttfs: list[Path],
    webfont_dir: Path,
    font_name: str,
    pool: Executor | None = None,
    variant: str = "default",
) -> list[dict]:
    """Write CSS to WEBFONT_DIR and slices to WEBFONT_DIR/<tag>/ (SC, Term-SC);
    return manifest entries."""
    ranges = load_slices(region)
    webfont_dir.mkdir(parents=True, exist_ok=True)
    tag = file_tag(variant, region)
    family = VARIANTS[variant].family_name(font_name, region)
    font_dir = webfont_dir / tag
    canonical = font_name.replace(" ", "")
    css_name = f"{canonical}-{tag}.css"
    style_css = {}
    default_rules = []
    expected = set()
    entries = []
    jobs = []

    # Publish only after every style succeeds.
    with tempfile.TemporaryDirectory(prefix=f".{region}-", dir=webfont_dir) as tmp:
        staging = Path(tmp)
        faces = []
        for input_ttf in input_ttfs:
            with TTFont(input_ttf) as font:
                points = set(font.getBestCmap() or {})
                weight = font["OS/2"].usWeightClass
                style = "italic" if font["OS/2"].fsSelection & 1 else "normal"
            if not points:
                raise RuntimeError(f"No Unicode cmap: {input_ttf}")
            faces.append((input_ttf, points, weight, style))
        universe = set().union(*(points for _, points, _, _ in faces))
        for input_ttf, points, weight, style in faces:
            slices = plan_slices(points, ranges, universe)
            groups = [group for group, _ in slices]
            if sum(map(len, groups)) != len(points) or set().union(*groups) != points:
                raise RuntimeError(f"Slices do not partition the cmap: {input_ttf}")
            ascii_points = PRINTABLE_ASCII & points
            if ascii_points and sum(bool(g & ascii_points) for g in groups) != 1:
                raise RuntimeError(f"Printable ASCII split across slices: {input_ttf}")
            css_slices = []
            names = []
            for idx, (group, urange) in enumerate(slices, 1):
                if not group:
                    continue
                name = f"{input_ttf.stem}.{idx}.woff2"
                jobs.append((input_ttf, staging / name, group))
                names.append(name)
                css_slices.append((idx, urange, f"{tag}/{name}"))
            expected.update(names)
            rule = generate_css(family, css_slices, weight, style)
            style_name = input_ttf.stem.rsplit("-", 1)[1]
            style_css[f"{canonical}-{tag}-{style_name}.css"] = rule
            if style_name in DEFAULT_CSS_STYLES:
                default_rules.append(rule)
            entries.append({
                "source": input_ttf.name,
                "source_sha256": sha256(input_ttf),
                "weight": weight,
                "style": style,
                "codepoints": len(points),
                "css": f"{canonical}-{tag}-{style_name}.css",
                "files": names,
            })
        run_jobs(jobs, pool)
        for entry in entries:
            entry["files"] = [
                {"file": f"{tag}/{name}", "sha256": sha256(staging / name)}
                for name in entry["files"]
            ]
            print(f"  {entry['source']}: {len(entry['files'])} slices, {entry['codepoints']} codepoints")
        style_css[css_name] = "\n".join(default_rules or style_css.values())
        for name, css in style_css.items():
            (staging / name).write_text(css, encoding="utf-8")
        font_dir.mkdir(exist_ok=True)
        for path in staging.glob("*.woff2"):
            path.replace(font_dir / path.name)
        for name in style_css:
            (staging / name).replace(webfont_dir / name)
        # CSS used to live inside the region directory.
        (font_dir / css_name).unlink(missing_ok=True)
        for old_style in ALL_STYLES:
            for stem in (f"{canonical}-{tag}-{old_style}", f"{canonical}{tag.replace('-', '')}-{old_style}"):
                for path in font_dir.glob(f"{stem}.*.woff2"):
                    if path.name not in expected:
                        path.unlink()
                (font_dir / f"{stem}.css").unlink(missing_ok=True)
                if f"{stem}.css" not in style_css:
                    (webfont_dir / f"{stem}.css").unlink(missing_ok=True)
    return entries


def run_jobs(jobs: list[tuple[Path, Path, set[int]]], pool: Executor | None) -> None:
    if pool is None:
        for job in jobs:
            subset_font(*job)
        return
    futures = [pool.submit(subset_font, *job) for job in jobs]
    try:
        for future in as_completed(futures):
            future.result()
    except BaseException:
        # Let running jobs finish before the staging directory is removed.
        for future in futures:
            future.cancel()
        wait(futures)
        raise


def write_extras(
    webfont_dir: Path, font_name: str, version: str, manifest: dict, variant: str = "default"
) -> None:
    """Add licenses, a usage README and a hash manifest for standalone publishing."""
    root = Path(__file__).parent
    shutil.copy2(root / "LICENSE", webfont_dir / "LICENSE")
    licenses = webfont_dir / "licenses"
    licenses.mkdir(exist_ok=True)
    for src, name in LICENSES.items():
        shutil.copy2(root / src, licenses / name)
    family = VARIANTS[variant].family_name(font_name, "SC")
    css = f"{font_name.replace(' ', '')}-{file_tag(variant, 'SC')}"
    (webfont_dir / "README.md").write_text(
        f"# {family.replace(' SC', '')} webfonts {version}\n\n"
        f"{variant} variant for SC / TC / JP / KR. `{css}.css` holds Regular,\n"
        f"Bold and their italics; `{css}-Light.css` and the like hold one\n"
        "style each. Browsers load only the slices a page uses.\n\n"
        "```html\n"
        f'<link rel="stylesheet" href="{css}.css">\n'
        f'<link rel="stylesheet" href="{css}-Light.css">\n'
        f"<style>code, pre {{ font-family: '{family}', monospace; }}</style>\n"
        "```\n\n"
        "Replace SC with TC, JP or KR for regional glyph forms. `manifest.json`\n"
        "lists source TTF and WOFF2 hashes. Fonts are licensed under the SIL Open\n"
        "Font License 1.1; see `LICENSE` and `licenses/`.\n",
        encoding="utf-8",
    )
    (webfont_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    ini = read_ini()
    font_name = ini.get("font_name", "PlemoCJK")
    version = ini.get("version", "dev")
    parser = argparse.ArgumentParser()
    parser.add_argument("build_dir", nargs="?", default=ini.get("build_fonts_dir", "build"))
    parser.add_argument("--variant", action="append", choices=list(VARIANTS),
                        help="variant to convert (repeatable; default: every built one)")
    args = parser.parse_args()
    build_dir = Path(args.build_dir)

    if not build_dir.exists():
        print(f"ERROR: {build_dir} not found", file=sys.stderr)
        sys.exit(1)

    canonical = font_name.replace(" ", "")
    inputs = {v: find_inputs(build_dir, canonical, v) for v in args.variant or VARIANTS}
    if args.variant:
        missing = [v for v, found in inputs.items() if not found]
        if missing:
            raise SystemExit(f"ERROR: no input fonts for variant(s): {', '.join(missing)}")
    inputs = {v: found for v, found in inputs.items() if found}
    if not inputs:
        raise SystemExit("ERROR: no input fonts found")

    with ProcessPoolExecutor(os.cpu_count()) as pool:
        for variant, regions in inputs.items():
            label = VARIANTS[variant].label
            webfont_dir = build_dir / "release" / (
                f"{canonical}-{label}_webfont_{version}" if label else f"{canonical}_webfont_{version}"
            )
            print(f"Output: {webfont_dir}")
            manifest = {
                "version": version,
                "variant": variant,
                "commit": os.environ.get("GITHUB_SHA") or git_commit(),
                "fonttools": fonttools_version,
                "regions": {},
            }
            for region, ttfs in regions.items():
                manifest["regions"][region] = process_region(
                    region, ttfs, webfont_dir, font_name, pool, variant
                )
            write_extras(webfont_dir, font_name, version, manifest, variant)
            print(f"\n### Done: {webfont_dir} ###")


if __name__ == "__main__":
    main()
