#!/usr/bin/env python3
"""Validate PlemoCJK build artifacts.

Checks:

1. Glyph count per sub-font and headroom up to 65,535
2. Whether codepoint sets match across all 4 regions
3. Coverage of JIS X 0208 / JIS X 0213 / GB 2312 / GBK / Big5 / KS X 1001
   (character sets are generated from Python built-in codecs)
4. Whether stroke widths of U+4E00 / U+4E28 are consistent across 8 weights x 4 regions (no exceptions)
5. Whether glyf is shared as a single block inside TTC
6. Whether test sentences in Chinese / Japanese / Korean produce no .notdef
7. Metadata (meta / OS/2 code page / fsSelection / hdmx / name)

Usage:
    python3 check_fonts.py                       # auto-detect build/
    python3 check_fonts.py --variant Console
    python3 check_fonts.py --prepared            # check source/prepared/
    python3 check_fonts.py --ttc build/ttc/PlemoCJKConsole-Regular.ttc
    python3 check_fonts.py --font-set SC=a.ttf,TC=b.ttf,JP=c.ttf,KR=d.ttf
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

import plemocjk_config

GLYPH_LIMIT = 0xFFFF

# Test sentences used for validation
TEST_SENTENCES = {
    "zh-Hans": "中文简体测试：汉字编码与排版，《红楼梦》第一回。数字 0123456789。",
    "zh-Hant": "中文繁體測試：漢字編碼與排版，《紅樓夢》第一回。數字 0123456789。",
    "ja": "日本語テスト：漢字・ひらがな・カタカナ、『吾輩は猫である』。半角ｶﾀｶﾅ。",
    "ko": "한국어 테스트: 한글과 한자(漢字)를 섞어 쓴 문장. 훈민정음 서문.",
    "mixed": "代码 コード 코드 code: if (x != y) { return 0; } 「全角」１２３",
}

# Glyphs for stroke width measurement. U+4E00 is horizontal (measured by height), U+4E28 is vertical (measured by width)
STROKE_GLYPHS = {0x4E00: "height", 0x4E28: "width"}
# Measured max spread across 8 weights x 4 regions is 3.0%
# (ExtraLight U+4E28 differs by 1 unit, 32 vs 33), so 5% is the threshold.
# IBM's SC Text had interpolation at 425 (5.6% thinner), but regen_sc_text.py
# regenerates it from the master at 450, so no exception is needed.
STROKE_TOLERANCE = 0.05


def log(*args) -> None:
    print(*args, flush=True)


# ---------------------------------------------------------------------------
# Character sets (generated from Python built-in codecs)
# ---------------------------------------------------------------------------
def decode_range(codec: str, leads, trails, prefix: bytes = b"") -> set[int]:
    result: set[int] = set()
    for lead in leads:
        for trail in trails:
            try:
                text = (prefix + bytes([lead, trail])).decode(codec)
            except Exception:  # noqa: BLE001 - skip undefined code positions
                continue
            result.update(ord(char) for char in text)
    return result


def standard_charsets() -> dict[str, tuple[set[int], bool]]:
    """Character set name -> (codepoint set, whether full coverage is required)"""
    euc = (range(0xA1, 0xFF), range(0xA1, 0xFF))
    jis_x_0208 = decode_range("euc_jp", *euc)
    jis_x_0213 = decode_range("euc_jis_2004", *euc) | decode_range(
        "euc_jis_2004", *euc, prefix=b"\x8f"
    )
    gb_2312 = decode_range("gb2312", *euc)
    gbk = decode_range("gbk", range(0x81, 0xFF), range(0x40, 0xFF))
    big5 = decode_range(
        "big5", range(0xA1, 0xFA), list(range(0x40, 0x7F)) + list(range(0xA1, 0xFF))
    )
    ks_x_1001 = decode_range("euc_kr", *euc)
    return {
        "JIS X 0208": (jis_x_0208, True),
        # U+2985 / U+2986 (white parentheses) are absent from all 4 IBM Plex Sans
        # variants, so full coverage is not required
        "JIS X 0213": (jis_x_0213, False),
        "GB 2312": (gb_2312, True),
        "GBK": (gbk, True),
        "Big5": (big5, True),
        "KS X 1001": (ks_x_1001, True),
    }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------
def check_glyph_counts(fonts: dict[str, TTFont]) -> list[str]:
    errors = []
    log("--- glyph counts ---")
    for region, font in fonts.items():
        count = font["maxp"].numGlyphs
        headroom = GLYPH_LIMIT - count
        status = "OK" if headroom > 0 else "OVER LIMIT"
        log(f"  {region}: {count:,} glyphs, headroom {headroom:,} ({status})")
        if headroom <= 0:
            errors.append(f"{region}: glyph count {count} exceeds {GLYPH_LIMIT}")
    return errors


def check_codepoint_consistency(fonts: dict[str, TTFont]) -> list[str]:
    errors = []
    log("--- codepoint set consistency ---")
    maps = {region: set(font.getBestCmap()) for region, font in fonts.items()}
    reference_region = next(iter(maps))
    reference = maps[reference_region]
    log(f"  reference {reference_region}: {len(reference):,} codepoints")
    for region, codepoints in maps.items():
        if codepoints == reference:
            log(f"  {region}: identical")
            continue
        only_here = sorted(codepoints - reference)
        only_there = sorted(reference - codepoints)
        log(
            f"  {region}: DIFFERS (+{len(only_here)} / -{len(only_there)})"
            f" e.g. +{[f'U+{c:04X}' for c in only_here[:5]]}"
            f" -{[f'U+{c:04X}' for c in only_there[:5]]}"
        )
        errors.append(
            f"{region}: codepoint set differs from {reference_region} "
            f"(+{len(only_here)} / -{len(only_there)})"
        )
    return errors


def check_standards(fonts: dict[str, TTFont]) -> list[str]:
    errors = []
    log("--- legacy charset coverage ---")
    charsets = standard_charsets()
    for region, font in fonts.items():
        codepoints = set(font.getBestCmap())
        parts = []
        for name, (charset, required) in charsets.items():
            missing = charset - codepoints
            parts.append(f"{name}:{len(missing)}")
            if missing and required:
                errors.append(
                    f"{region}: {name} missing {len(missing)} codepoints "
                    f"(e.g. {', '.join(f'U+{c:04X}' for c in sorted(missing)[:5])})"
                )
        log(f"  {region}: missing " + "  ".join(parts))
    return errors


def check_hangul(fonts: dict[str, TTFont], config: plemocjk_config.Config) -> list[str]:
    errors = []
    log("--- hangul ---")
    hangul = config.hangul_codepoints()
    half_width_hangul = config.half_width_hangul_codepoints()
    syllables = set(range(0xAC00, 0xD7A4))
    for region, font in fonts.items():
        cmap = font.getBestCmap()
        hmtx = font["hmtx"]
        present = hangul & set(cmap)
        missing_syllables = syllables - set(cmap)
        widths = {hmtx[cmap[cp]][0] for cp in syllables if cp in cmap}
        half = {hmtx[cmap[cp]][0] for cp in half_width_hangul if cp in cmap}
        log(
            f"  {region}: {len(present):,} hangul codepoints, "
            f"{len(syllables) - len(missing_syllables):,}/11172 syllables, "
            f"advance widths {sorted(widths)}"
            + (f", halfwidth-jamo widths {sorted(half)}" if half else "")
        )
        if missing_syllables:
            errors.append(
                f"{region}: {len(missing_syllables)} hangul syllables missing"
            )
        if len(widths) > 1:
            errors.append(f"{region}: hangul syllables have mixed widths {widths}")
    return errors


def check_notdef(fonts: dict[str, TTFont]) -> list[str]:
    errors = []
    log("--- test sentences (.notdef check) ---")
    for region, font in fonts.items():
        cmap = font.getBestCmap()
        bad = []
        for label, sentence in TEST_SENTENCES.items():
            for char in sentence:
                name = cmap.get(ord(char))
                if name is None or name == ".notdef":
                    bad.append(f"{label}:{char!r} U+{ord(char):04X}")
        if bad:
            log(f"  {region}: {len(bad)} missing -> {', '.join(bad[:6])}")
            errors.append(f"{region}: {len(bad)} test-sentence characters missing")
        else:
            log(f"  {region}: all {len(TEST_SENTENCES)} sentences fully covered")
    return errors


def glyph_bounds(font: TTFont, codepoint: int):
    cmap = font.getBestCmap()
    name = cmap.get(codepoint)
    if name is None:
        return None
    glyph_set = font.getGlyphSet()
    pen = BoundsPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.bounds


def check_stroke_weights(
    font_paths: dict[tuple[str, str], Path], config: plemocjk_config.Config
) -> list[str]:
    """Whether stroke widths of U+4E00 / U+4E28 are consistent across all 8 weights x 4 regions.

    No exceptions. IBM's SC Text alone had interpolation at 425 (5.6% thinner
    than other regions at 450), so regen_sc_text.py regenerates it from the
    master at 450 (configured via REGENERATED_STYLES in build.ini).
    """
    errors = []
    log("--- stroke weight consistency (U+4E00 / U+4E28) ---")
    styles = sorted({style for _, style in font_paths})
    for style in styles:
        for codepoint, axis in STROKE_GLYPHS.items():
            measures: dict[str, float] = {}
            for region in config.regions:
                path = font_paths.get((region, style))
                if path is None:
                    continue
                font = TTFont(path, lazy=True)
                bounds = glyph_bounds(font, codepoint)
                font.close()
                if bounds is None:
                    continue
                x_min, y_min, x_max, y_max = bounds
                measures[region] = (
                    y_max - y_min if axis == "height" else x_max - x_min
                )
            if len(measures) < 2:
                continue
            values = list(measures.values())
            lowest, highest = min(values), max(values)
            spread = (highest - lowest) / highest if highest else 0.0
            detail = "  ".join(f"{r}={v:.0f}" for r, v in measures.items())
            if spread <= STROKE_TOLERANCE:
                log(f"  U+{codepoint:04X} {style}: {detail} (spread {spread:.1%})")
                continue
            log(f"  U+{codepoint:04X} {style}: {detail} (spread {spread:.1%}) FAIL")
            errors.append(
                f"U+{codepoint:04X} {style}: stroke weight spread {spread:.1%} "
                f"exceeds {STROKE_TOLERANCE:.0%} ({detail})"
            )
    return errors


def check_metadata(
    fonts: dict[str, TTFont], config: plemocjk_config.Config, wmode: str
) -> list[str]:
    errors = []
    log("--- metadata ---")
    for region, font in fonts.items():
        region_config = config.regions[region]
        meta = font["meta"].data if "meta" in font else {}
        os2 = font["OS/2"]
        name = font["name"]
        family = name.getDebugName(1)
        expected_bits = 0
        for bit in region_config.code_page_bits:
            if bit < 32:
                expected_bits |= 1 << bit
        localized = sorted(
            {
                record.langID
                for record in name.names
                if record.nameID == 1 and record.platformID == 3
            }
        )
        has_hdmx = "hdmx" in font
        log(
            f"  {region}: family={family!r} meta={meta} "
            f"cp1=0x{os2.ulCodePageRange1:08X} "
            f"USE_TYPO={'yes' if os2.fsSelection & 0x80 else 'no'} "
            f"hdmx={'yes' if has_hdmx else 'no'} "
            f"name1 langs={[f'0x{x:04X}' for x in localized]}"
        )
        if meta.get("dlng") != region_config.meta_dlng:
            errors.append(f"{region}: meta dlng {meta.get('dlng')!r}")
        if meta.get("slng") != region_config.meta_slng:
            errors.append(f"{region}: meta slng {meta.get('slng')!r}")
        if os2.ulCodePageRange1 != expected_bits:
            errors.append(
                f"{region}: ulCodePageRange1 0x{os2.ulCodePageRange1:08X} "
                f"!= 0x{expected_bits:08X}"
            )
        if not os2.fsSelection & 0x80:
            errors.append(f"{region}: fsSelection is missing USE_TYPO_METRICS")
        if region not in (family or ""):
            errors.append(f"{region}: family name {family!r} lacks the region token")
        for locale in region_config.localized_labels:
            lang_id = plemocjk_config.WINDOWS_LANG_IDS.get(locale)
            if lang_id is not None and lang_id not in localized:
                errors.append(f"{region}: missing localized family name for {locale}")
        expect_hdmx = wmode != "35"
        if not expect_hdmx and has_hdmx:
            errors.append(f"{region}: 3:5 variant must not carry hdmx")
        if expect_hdmx:
            if not has_hdmx:
                errors.append(f"{region}: {wmode} variant is missing hdmx")
            elif not font["head"].flags & 0x0010:
                errors.append(f"{region}: head.flags bit 4 (0x0010) is not set")
            else:
                errors.extend(check_hdmx_ratio(region, font))
    return errors


def check_hdmx_ratio(region: str, font: TTFont) -> list[str]:
    """Whether hdmx ensures full-width == 2 x half-width"""
    cmap = font.getBestCmap()
    hdmx = font["hdmx"].hdmx
    half_glyph = cmap.get(0x0041)  # A
    full_glyph = cmap.get(0x4E00)  # 一
    if half_glyph is None or full_glyph is None:
        return []
    for ppem, widths in sorted(hdmx.items()):
        half = widths[half_glyph]
        full = widths[full_glyph]
        if full != half * 2:
            return [
                f"{region}: hdmx ppem {ppem}: full {full} != 2 x half {half}"
            ]
    return []


# ---------------------------------------------------------------------------
# TTC
# ---------------------------------------------------------------------------
def read_ttc_layout(path: Path) -> tuple[int, dict[str, list[tuple[int, int]]]]:
    """Read a TTC file raw and return per-tag lists of (offset, length)"""
    data = path.read_bytes()
    tag, _major, _minor, num_fonts = struct.unpack(">4sHHL", data[:12])
    if tag != b"ttcf":
        raise ValueError(f"{path} is not a TTC (tag {tag!r})")
    offsets = struct.unpack(f">{num_fonts}L", data[12 : 12 + 4 * num_fonts])
    tables: dict[str, list[tuple[int, int]]] = {}
    for font_offset in offsets:
        num_tables = struct.unpack(">H", data[font_offset + 4 : font_offset + 6])[0]
        for index in range(num_tables):
            base = font_offset + 12 + index * 16
            table_tag, _checksum, offset, length = struct.unpack(
                ">4sLLL", data[base : base + 16]
            )
            tables.setdefault(table_tag.decode("latin-1"), []).append((offset, length))
    return num_fonts, tables


def check_ttc(path: Path, config: plemocjk_config.Config) -> list[str]:
    errors = []
    log(f"--- TTC {path} ---")
    num_fonts, tables = read_ttc_layout(path)
    expected = len(config.ttc_order)
    log(f"  subfonts: {num_fonts} (expected {expected})")
    if num_fonts != expected:
        errors.append(f"{path.name}: {num_fonts} subfonts, expected {expected}")

    shared = []
    for tag in sorted(tables):
        copies = len(set(tables[tag]))
        total = len(tables[tag])
        size = sum(length for _, length in set(tables[tag]))
        shared.append(f"{tag}:{copies}/{total}")
        if tag == "glyf":
            log(f"  glyf: {copies} distinct block(s) of {total}, {size / 1e6:.1f}MB")
            if copies != 1:
                errors.append(
                    f"{path.name}: glyf is stored {copies} times, expected 1 "
                    "(sparse glyph sharing did not kick in)"
                )
    log("  table copies: " + "  ".join(shared))

    # Verify fontTools can open it / each sub-font's cmap is correct
    from fontTools.ttLib import TTCollection

    collection = TTCollection(str(path), lazy=True)
    try:
        log(f"  opened with fontTools: {len(collection.fonts)} fonts")

        # glyf sharing rate: collect glyph data ranges from each sub-font's loca,
        # then compare distinct count vs. total
        blocks: set[tuple[int, int]] = set()
        total_glyphs = 0
        for font in collection.fonts:
            loca = font["loca"]
            count = font["maxp"].numGlyphs
            total_glyphs += count
            for index in range(count):
                blocks.add((loca[index], loca[index + 1]))
        if total_glyphs:
            log(
                f"  glyf sharing: {total_glyphs:,} glyph slots -> "
                f"{len(blocks):,} distinct data blocks "
                f"({1 - len(blocks) / total_glyphs:.1%} shared)"
            )

        reference = None
        for index, font in enumerate(collection.fonts):
            family = font["name"].getDebugName(1)
            meta = font["meta"].data if "meta" in font else {}
            codepoints = set(font.getBestCmap())
            log(
                f"    [{index}] {family!r} glyphs={font['maxp'].numGlyphs:,} "
                f"codepoints={len(codepoints):,} dlng={meta.get('dlng')}"
            )
            expected_region = config.ttc_order[index] if index < expected else None
            if expected_region and expected_region not in (family or ""):
                errors.append(
                    f"{path.name}: subfont {index} family {family!r} "
                    f"does not match expected region {expected_region}"
                )
            if reference is None:
                reference = codepoints
            elif codepoints != reference:
                errors.append(
                    f"{path.name}: subfont {index} cmap differs from subfont 0 "
                    f"(+{len(codepoints - reference)} / -{len(reference - codepoints)})"
                )
            for sentence in TEST_SENTENCES.values():
                cmap = font.getBestCmap()
                bad = [c for c in sentence if cmap.get(ord(c), ".notdef") == ".notdef"]
                if bad:
                    errors.append(
                        f"{path.name}: subfont {index} cannot render {bad[:4]}"
                    )
                    break
    finally:
        collection.close()
    return errors


# ---------------------------------------------------------------------------
# Input discovery
# ---------------------------------------------------------------------------
def discover(
    config: plemocjk_config.Config, variant: str | None, directory: Path
) -> dict[tuple[str, str], Path]:
    """Discover font files per variant.

    When --variant is not specified and build/ contains multiple variants,
    (region, weight) keys would collide and mix, so we pick the single
    variant with the most files.
    """
    per_variant: dict[str, dict[tuple[str, str], Path]] = {}
    variants = [variant] if variant else list(plemocjk_config.VARIANTS)
    for name in variants:
        found: dict[tuple[str, str], Path] = {}
        for region in config.regions:
            tag = config.variant_tag(name, region)
            for style in plemocjk_config.ALL_STYLES:
                htag = plemocjk_config.hyphenate_tag(tag)
                path = directory / f"{config.font_name}-{htag}-{style}.ttf"
                if path.is_file():
                    found[(region, style)] = path
        if found:
            per_variant[name] = found

    if not per_variant:
        return {}
    if len(per_variant) > 1:
        chosen = max(per_variant, key=lambda name: len(per_variant[name]))
        log(
            f"note: {len(per_variant)} variants found in {directory} "
            f"({', '.join(sorted(per_variant))}); checking {chosen}. "
            "Pass --variant to pick another."
        )
        return per_variant[chosen]
    return next(iter(per_variant.values()))


def main() -> int:
    config = plemocjk_config.load()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", default=None, help="variant to check")
    parser.add_argument(
        "--dir", default=None, help="directory to check (default: build/)"
    )
    parser.add_argument(
        "--prepared",
        action="store_true",
        help="check CJK input fonts in source/prepared/",
    )
    parser.add_argument("--ttc", action="append", default=[], help="TTC file to check")
    parser.add_argument(
        "--font-set",
        default=None,
        help="specify region=path pairs directly, comma-separated (e.g. SC=a.ttf,TC=b.ttf)",
    )
    parser.add_argument(
        "--style", default="Regular", help="weight to use for main checks (default: Regular)"
    )
    args = parser.parse_args()

    errors: list[str] = []
    font_paths: dict[tuple[str, str], Path] = {}

    # When only --ttc is given, run TTC checks only
    ttc_only = bool(args.ttc) and not (
        args.variant or args.font_set or args.prepared or args.dir
    )

    if ttc_only:
        pass
    elif args.font_set:
        for item in args.font_set.split(","):
            region, _, path = item.partition("=")
            font_paths[(region.strip(), args.style)] = Path(path.strip())
    elif args.prepared:
        directory = Path(args.dir) if args.dir else config.source_dir / "prepared"
        for region in config.regions:
            for style in plemocjk_config.UPRIGHT_STYLES:
                path = directory / f"{config.font_name}-{region}-{style}.ttf"
                if path.is_file():
                    font_paths[(region, style)] = path
    else:
        directory = Path(args.dir) if args.dir else config.build_dir
        font_paths = discover(config, args.variant, directory)

    if not font_paths and not args.ttc:
        print(
            "ERROR: no fonts found to check. "
            "Build with make.sh or specify --dir / --font-set.",
            file=sys.stderr,
        )
        return 2

    if font_paths:
        styles = sorted({style for _, style in font_paths})
        main_style = args.style if any(s == args.style for _, s in font_paths) else styles[0]
        fonts: dict[str, TTFont] = {}
        for region in config.regions:
            path = font_paths.get((region, main_style))
            if path is not None:
                fonts[region] = TTFont(path, lazy=True)
        log(f"=== fonts: {len(font_paths)} files, main style {main_style} ===")
        for region, font in fonts.items():
            log(f"  {region}: {font_paths[(region, main_style)]}")

        try:
            errors += check_glyph_counts(fonts)
            errors += check_codepoint_consistency(fonts)
            errors += check_standards(fonts)
            errors += check_hangul(fonts, config)
            errors += check_notdef(fonts)
            if not args.prepared:
                fname = font_paths[(next(iter(fonts)), main_style)].stem
                parts = fname.removeprefix(config.font_name + "-").split("-")
                variant_tag = "".join(parts[:-1])
                wmode = plemocjk_config.width_mode_for_tag(variant_tag)
                errors += check_metadata(fonts, config, wmode)
            errors += check_stroke_weights(font_paths, config)
        finally:
            for font in fonts.values():
                font.close()

    for ttc in args.ttc:
        errors += check_ttc(Path(ttc), config)

    log("")
    if errors:
        log(f"=== {len(errors)} problem(s) ===")
        for message in errors:
            log(f"FAIL: {message}")
        return 1
    log("=== all checks passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
