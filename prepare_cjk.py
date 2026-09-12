#!/usr/bin/env python3
"""Build region-specific CJK input fonts (PlemoCJK).

Each region uses its own IBM Plex Sans as the primary font and fills in
missing codepoints from other regions' fonts (fallback fill). Output goes to
source/prepared/PlemoCJK-{region}-{style}.ttf, which fontforge_script.py
reads instead of JP_FONT when --region is specified.

Design invariants:

1. Existing glyphs are never overwritten. Codepoints present in the primary
   region always use the primary region's glyphs.
2. Fallback order follows FALLBACK_{region} in build.ini:
   SC <- JP <- TC <- KR / TC <- SC <- JP <- KR /
   JP <- SC <- TC <- KR / KR <- JP <- SC <- TC
   Every region ends up with the union of all four regions' codepoints,
   so the coverage of the four sub-fonts is identical.
   (Hangul appearing in all regions is a consequence of this rule.)
3. Only the primary region's GSUB is kept. Donor GSUB/GPOS are discarded.
   No locl for ideographs (region-specific sub-fonts handle the distinction).
4. (region, weight) pairs listed in REGENERATED_STYLES in build.ini use
   fonts rebuilt from the Glyphs master by regen_sc_text.py instead of
   the IBM release. Currently only SC Text (the release is interpolated at
   weight 425, about 5% thinner than JP/TC at 450).
5. TrueType instructions are dropped by default, for two reasons:
   - Hinting is applied to the Latin side by ttfautohint later (same as
     upstream PlemolJP).
   - The KR source contains instructions that depend on fpgm/prep/cvt;
     carrying them into the destination font breaks rendering. Dropping
     them makes Hangul glyphs byte-identical across all regions, enabling
     glyf sharing in the TTC.

Usage:
    python3 prepare_cjk.py                          # 4 regions x 8 weights
    python3 prepare_cjk.py --regions SC --styles Regular
    python3 prepare_cjk.py --report                 # print fill statistics only
    python3 prepare_cjk.py --font-template '/tmp/plex/ttf/{region}-{style}.ttf'
"""

from __future__ import annotations

import argparse
import copy
import sys
import unicodedata
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

import plemocjk_config

# Tables to exclude when importing from donor fonts
DROP_FROM_DONOR = [
    "GSUB",
    "GPOS",
    "GDEF",
    "BASE",
    "JSTF",
    "DSIG",
    "MATH",
    "meta",
    "STAT",
    "kern",
    "vhea",
    "vmtx",
    "VORG",
]

# Tables to remove when stripping hinting
HINTING_TABLES = ["fpgm", "prep", "cvt ", "gasp", "hdmx", "LTSH", "VDMX"]


def log(*args) -> None:
    print(*args, flush=True)


def open_font(path: Path) -> TTFont:
    return TTFont(str(path), recalcBBoxes=False, recalcTimestamp=False)


def codepoints_of(path: Path) -> set[int]:
    font = TTFont(str(path), lazy=True)
    try:
        return set(font.getBestCmap())
    finally:
        font.close()


def drop_hints(font: TTFont) -> None:
    """Strip TrueType instructions and related tables from glyphs."""
    glyf = font["glyf"]
    for name in font.getGlyphOrder():
        glyph = glyf[name]  # __getitem__ calls expand() and discards .data
        if glyph.isComposite():
            # For composites, WE_HAVE_INSTRUCTIONS is determined by the presence of program
            if hasattr(glyph, "program"):
                del glyph.program
        elif glyph.numberOfContours > 0:
            # Simple glyphs: compile() always references program, so clear it
            glyph.program = ttProgram.Program()
            glyph.program.fromBytecode(b"")
        elif hasattr(glyph, "program"):
            del glyph.program
    for tag in HINTING_TABLES:
        if tag in font:
            del font[tag]
    # Zero out hinting-related limits in maxp
    maxp = font["maxp"]
    for attr in (
        "maxZones",
        "maxTwilightPoints",
        "maxStorage",
        "maxFunctionDefs",
        "maxInstructionDefs",
        "maxStackElements",
        "maxSizeOfInstructions",
    ):
        if hasattr(maxp, attr):
            setattr(maxp, attr, 0)
    maxp.maxZones = 1


def base_options(keep_hints: bool) -> subset.Options:
    options = subset.Options()
    options.glyph_names = True
    options.notdef_outline = False
    options.recalc_bounds = False
    options.recalc_timestamp = False
    options.hinting = keep_hints
    options.legacy_cmap = False
    options.symbol_cmap = False
    options.ignore_missing_unicodes = True
    return options


def subset_donor(path: Path, codepoints: set[int], keep_hints: bool) -> TTFont:
    """Subset a donor font to only the needed codepoints."""
    font = open_font(path)
    options = base_options(keep_hints)
    options.layout_features = []  # discard all GSUB/GPOS features
    options.name_IDs = []
    options.name_languages = []
    options.drop_tables = list(set(options.drop_tables) | set(DROP_FROM_DONOR))
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=codepoints)
    subsetter.subset(font)
    return font


def load_primary(path: Path, keep_features: list[str], keep_hints: bool) -> TTFont:
    """Open the primary region font, dropping unwanted GSUB features and their glyphs.

    GPOS is dropped here because upstream fontforge_script.py removes all
    lookups anyway (FontForge gets slow with ~48,000 glyphs).
    vhea/vmtx are also dropped here since upstream fonttools_script.py's
    merge_fonts deletes them (no point generating vertical metrics for
    filled-in glyphs).
    """
    font = open_font(path)
    options = base_options(keep_hints)
    options.layout_features = list(keep_features)
    options.drop_tables = list(
        set(options.drop_tables)
        | {"GPOS", "DSIG", "meta", "BASE", "JSTF", "vhea", "vmtx", "VORG"}
    )
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=set(font.getBestCmap()))
    subsetter.subset(font)
    return font


def graft(primary: TTFont, donor: TTFont, suffix: str) -> dict[int, str]:
    """Add all donor glyphs to the primary font and return a cmap mapping.

    Glyph names are suffixed to avoid collisions. Composite references are
    remapped accordingly.
    """
    primary_glyf = primary["glyf"]
    primary_hmtx = primary["hmtx"]
    order = list(primary.getGlyphOrder())
    taken = set(order)

    donor_glyf = donor["glyf"]
    donor_hmtx = donor["hmtx"]

    rename: dict[str, str] = {}
    added: list[str] = []
    for name in donor.getGlyphOrder():
        if name == ".notdef":
            continue
        candidate = f"{name}{suffix}"
        index = 0
        while candidate in taken:
            index += 1
            candidate = f"{name}{suffix}{index}"
        taken.add(candidate)
        rename[name] = candidate
        added.append(candidate)

    for name, new_name in rename.items():
        glyph = copy.deepcopy(donor_glyf[name])
        if glyph.isComposite():
            for component in glyph.components:
                # composites referencing .notdef should not exist, but guard anyway
                component.glyphName = rename.get(
                    component.glyphName, component.glyphName
                )
        primary_glyf.glyphs[new_name] = glyph
        primary_hmtx.metrics[new_name] = donor_hmtx.metrics[name]

    new_order = order + added
    primary.setGlyphOrder(new_order)
    primary_glyf.glyphOrder = new_order
    # Invalidate the getGlyphID cache
    if hasattr(primary, "_reverseGlyphOrderDict"):
        del primary._reverseGlyphOrderDict
    primary["maxp"].numGlyphs = len(new_order)

    return {cp: rename[name] for cp, name in donor.getBestCmap().items()}


def make_cmap_subtable(
    platform_id: int, plat_enc_id: int, fmt: int, mapping: dict[int, str]
) -> CmapSubtable:
    subtable = CmapSubtable.newSubtable(fmt)
    subtable.platformID = platform_id
    subtable.platEncID = plat_enc_id
    subtable.language = 0
    subtable.cmap = dict(mapping)
    return subtable


def rebuild_cmap(font: TTFont, mapping: dict[int, str]) -> None:
    """Rebuild Unicode cmap subtables from the given mapping.

    Legacy Mac subtables are discarded.
    Format 4 length is uint16, so fragmented glyph IDs from fallback fill
    can exceed 64KB. In that case only format 12 is written (only FontForge
    reads this intermediate file, so this is fine).
    """
    bmp = {cp: name for cp, name in mapping.items() if cp <= 0xFFFF}

    tables = [
        make_cmap_subtable(3, 10, 12, mapping),
        make_cmap_subtable(0, 4, 12, mapping),
    ]

    # Include format 4 for compatibility if it fits
    candidate = make_cmap_subtable(3, 1, 4, bmp)
    font["cmap"].tableVersion = 0
    font["cmap"].tables = tables + [candidate]
    try:
        if len(candidate.compile(font)) <= 0xFFFF:
            tables = [candidate, make_cmap_subtable(0, 3, 4, bmp)] + tables
        else:
            raise ValueError("cmap format 4 subtable too large")
    except Exception:
        log(
            "    note: cmap format 4 does not fit (fragmented glyph IDs); "
            "writing format 12 only"
        )
    font["cmap"].tables = tables


# CJK compatibility ideograph blocks (those whose canonical decomposition is a single unified ideograph)
COMPAT_IDEOGRAPH_RANGES = ((0xF900, 0xFAFF), (0x2F800, 0x2FA1D))


def compat_ideograph_aliases(mapping: dict[int, str]) -> dict[int, str]:
    """Return aliases mapping CJK compatibility ideographs to their canonical unified ideograph glyphs.

    IBM Plex Sans has no glyphs for this block, which would leave 268 KS X 1001
    characters (and some GBK characters) missing. These are canonically equivalent
    to unified ideographs (singleton decomposition), so pointing them at the same
    glyph is semantically correct. No new glyphs are added.
    """
    aliases: dict[int, str] = {}
    for start, end in COMPAT_IDEOGRAPH_RANGES:
        for cp in range(start, end + 1):
            if cp in mapping:
                continue
            decomposition = unicodedata.decomposition(chr(cp))
            if not decomposition or decomposition.startswith("<"):
                continue
            parts = decomposition.split()
            if len(parts) != 1:
                continue
            target = int(parts[0], 16)
            if target in mapping:
                aliases[cp] = mapping[target]
    return aliases


def make_cmap_injective(font: TTFont, mapping: dict[int, str]) -> int:
    """Eliminate cases where multiple codepoints share a single glyph.

    FontForge reads these as altuni entries, but upstream fontforge_script.py's
    delete_duplicate_glyphs / materialize_altuni_glyphs fails to handle cases
    where one of the aliases also exists on the Latin side, causing clear() to
    drop the shared glyph and lose the other codepoint.

    In practice, some of IBM Plex Sans TC's Big5/HKSCS aliases (4,900+) collide
    with Powerline PUA (U+E0A0-E0D4), causing 35 codepoints such as U+542F and
    U+FF5E to disappear from the TC sub-font.

    Giving each codepoint its own glyph instance prevents altuni from arising,
    eliminating this problem by design. The glyph bytes are identical, so TTC
    glyf sharing is unaffected.
    """
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    order = list(font.getGlyphOrder())
    taken = set(order)

    by_glyph: dict[str, list[int]] = {}
    for codepoint, name in mapping.items():
        by_glyph.setdefault(name, []).append(codepoint)

    added: list[str] = []
    for name in sorted(by_glyph):
        codepoints = sorted(by_glyph[name])
        if len(codepoints) < 2:
            continue
        # The lowest codepoint keeps the original glyph; the rest get copies
        for codepoint in codepoints[1:]:
            candidate = f"u{codepoint:04X}.alias"
            index = 0
            while candidate in taken:
                index += 1
                candidate = f"u{codepoint:04X}.alias{index}"
            taken.add(candidate)
            glyf.glyphs[candidate] = copy.deepcopy(glyf[name])
            hmtx.metrics[candidate] = hmtx.metrics[name]
            mapping[codepoint] = candidate
            added.append(candidate)

    if added:
        new_order = order + added
        font.setGlyphOrder(new_order)
        glyf.glyphOrder = new_order
        if hasattr(font, "_reverseGlyphOrderDict"):
            del font._reverseGlyphOrderDict
        font["maxp"].numGlyphs = len(new_order)
    return len(added)


def set_names(font: TTFont, font_name: str, region: str, style: str) -> None:
    """Set human-readable names for build logs and temporary file identification.

    The final name table is produced by fontforge_script.py / fonttools_script.py.
    """
    family = f"{font_name} CJK {region}"
    full = f"{family} {style}"
    postscript = f"{font_name}CJK{region}-{style}"
    name_table = font["name"]
    for name_id, value in (
        (1, family),
        (2, style),
        (3, f"{full};PlemoCJK-prepared"),
        (4, full),
        (6, postscript),
        (16, family),
        (17, style),
    ):
        name_table.setName(value, name_id, 3, 1, 0x0409)
        name_table.setName(value, name_id, 1, 0, 0)


def prepare_one(
    config: plemocjk_config.Config,
    region: str,
    style: str,
    paths: dict[str, Path],
    target: set[int],
    out_path: Path,
    keep_hints: bool,
) -> dict[str, int]:
    """Build the CJK input font for one region and one weight."""
    primary = load_primary(paths[region], config.gsub_keep_features, keep_hints)
    mapping = dict(primary.getBestCmap())
    for cp in config.exclude_codepoints:
        mapping.pop(cp, None)

    if not keep_hints:
        drop_hints(primary)

    stats: dict[str, int] = {region: len(mapping)}

    for donor_name in config.regions[region].fallback:
        need = {cp for cp in target if cp not in mapping}
        if not need:
            stats[donor_name] = 0
            continue
        available = need & codepoints_of(paths[donor_name])
        stats[donor_name] = len(available)
        if not available:
            continue
        donor = subset_donor(paths[donor_name], available, keep_hints)
        if not keep_hints:
            drop_hints(donor)
        added = graft(primary, donor, f".{donor_name.lower()}")
        donor.close()
        for cp, name in added.items():
            if cp in mapping:  # safety: never overwrite existing glyphs
                continue
            mapping[cp] = name

    if config.alias_compat_ideographs:
        aliases = compat_ideograph_aliases(mapping)
        mapping.update(aliases)
        stats["_compat_aliases"] = len(aliases)

    missing = target - set(mapping)
    if missing:
        log(
            f"  WARNING: {region}-{style}: {len(missing)} codepoints still missing "
            f"(first: {', '.join(f'U+{cp:04X}' for cp in sorted(missing)[:8])})"
        )

    stats["_aliases_resolved"] = make_cmap_injective(primary, mapping)

    rebuild_cmap(primary, mapping)
    set_names(primary, config.font_name, region, style)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    primary.save(str(out_path))
    primary.close()

    stats["_glyphs"] = primary["maxp"].numGlyphs
    stats["_codepoints"] = len(mapping)
    return stats


def main() -> int:
    config = plemocjk_config.load()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regions",
        default=",".join(config.regions),
        help="対象地域 (カンマ区切り)",
    )
    parser.add_argument(
        "--styles",
        default=",".join(plemocjk_config.UPRIGHT_STYLES),
        help="対象ウェイト (カンマ区切り)",
    )
    parser.add_argument(
        "--font-template",
        default=None,
        help="ソースフォントのパステンプレート ({region} / {style} を置換)。"
        "既定は build.ini の REGION_SOURCE_FONT",
    )
    parser.add_argument("--out-dir", default=None, help="出力先 (既定: source/prepared)")
    parser.add_argument(
        "--report",
        action="store_true",
        help="フォントを書かず、補入されるコードポイント数の集計だけ出す",
    )
    parser.add_argument(
        "--keep-hints",
        action="store_true",
        help="TrueType 命令を残す (既定は落とす)",
    )
    args = parser.parse_args()

    regions = plemocjk_config.parse_list(args.regions)
    styles = plemocjk_config.parse_list(args.styles)
    unknown = [r for r in regions if r not in config.regions]
    if unknown:
        print(f"ERROR: unknown region(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    def source_path(region: str, style: str) -> Path:
        if args.font_template:
            return Path(
                args.font_template.replace("{region}", region).replace("{style}", style)
            )
        return config.region_source_path(region, style)

    hangul = config.hangul_codepoints() if args.report else set()

    def is_regenerated(region: str, style: str) -> bool:
        # When --font-template is given explicitly, it applies to all regions
        return args.font_template is None and config.is_regenerated(region, style)

    for style in styles:
        paths = {r: source_path(r, style) for r in config.regions}
        missing = {r: p for r, p in paths.items() if not p.is_file()}
        if missing:
            print(
                "ERROR: source font(s) not found:\n  "
                + "\n  ".join(str(p) for p in missing.values()),
                file=sys.stderr,
            )
            if any(is_regenerated(r, style) for r in missing):
                print(
                    "  build.ini の REGENERATED_STYLES で母版から作り直す指定に"
                    "なっているウェイトです。\n"
                    "  python3 regen_sc_text.py を先に実行してください",
                    file=sys.stderr,
                )
            if any(not is_regenerated(r, style) for r in missing):
                print(
                    "  python3 fetch_sources.py を先に実行してください",
                    file=sys.stderr,
                )
            return 1

        all_codepoints = {r: codepoints_of(p) for r, p in paths.items()}
        target = set().union(*all_codepoints.values()) - config.exclude_codepoints

        log(f"=== {style} === target codepoints: {len(target)}")
        for region in config.regions:
            if is_regenerated(region, style):
                log(f"  {region}: regenerated source {paths[region]}")

        for region in regions:
            if args.report:
                have = set(all_codepoints[region]) - config.exclude_codepoints
                parts = []
                for donor in config.regions[region].fallback:
                    need = (target - have) & all_codepoints[donor]
                    hangul_part = len(need & hangul)
                    parts.append(
                        f"{donor}:{len(need)}"
                        + (f" (hangul {hangul_part})" if hangul_part else "")
                    )
                    have |= need
                log(
                    f"  {region}: own={len(all_codepoints[region])} "
                    f"filled={len(have) - len(all_codepoints[region] - config.exclude_codepoints)} "
                    f"[{', '.join(parts)}] -> total={len(have)} "
                    f"missing={len(target - have)}"
                )
                continue

            out_path = (
                Path(args.out_dir) / f"PlemoCJK-{region}-{style}.ttf"
                if args.out_dir
                else config.prepared_path(region, style)
            )
            log(f"  build {out_path}")
            stats = prepare_one(
                config, region, style, paths, target, out_path, args.keep_hints
            )
            filled = ", ".join(
                f"{k}:{v}"
                for k, v in stats.items()
                if not k.startswith("_") and k != region
            )
            log(
                f"    own={stats[region]} filled[{filled}] "
                f"compat_aliases={stats.get('_compat_aliases', 0)} "
                f"dealiased={stats.get('_aliases_resolved', 0)} "
                f"glyphs={stats['_glyphs']} codepoints={stats['_codepoints']} "
                f"size={out_path.stat().st_size / 1e6:.1f}MB"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
