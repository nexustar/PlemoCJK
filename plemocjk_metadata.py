#!/usr/bin/env python3
"""Finalize metadata for region-specific sub-fonts (PlemoCJK).

Called after fonttools_script.py has built each region's TTF. Steps:

1. Rewrite the name table family name to include the region.
   The alphanumeric side (eng) is region-independent, so it is built without a
   region token; fontTools merge adopts the name table of the first font (= eng),
   so we must rewrite the family name to include the region here.
2. Add localized family names for zh_CN / zh_TW / ja / ko.
3. Populate the meta table with dlng / slng (used for font selection hints).
4. Set OS/2 ulCodePageRange according to the region.
5. Set USE_TYPO_METRICS in fsSelection.
6. For 1:2-width variants (12 and 36 modes), add hdmx and set the
   "instructions may depend on point size" bit in head.flags.
   Not applied to 3:5-width variants because 5 * half_px == 3 * full_px
   has no integer solution.

Can be run standalone on any TTF:
    python3 plemocjk_metadata.py build/PlemoCJK-Console-SC-Regular.ttf SC ConsoleSC Regular
"""

from __future__ import annotations

import math
import sys

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._m_e_t_a import table__m_e_t_a

import plemocjk_config

USE_TYPO_METRICS = 1 << 7
# head.flags bit 4: Instructions may depend on point size
HEAD_FLAG_INSTRUCTIONS_DEPEND_ON_PPEM = 0x0010

NAME_IDS_TO_REWRITE = (1, 2, 3, 4, 6, 16, 17)
BASIC_STYLES = ("Regular", "Italic", "Bold", "BoldItalic")


def weight_display(style: str) -> str:
    """"ThinItalic" -> "Thin Italic" (same rule as upstream PlemolJP)"""
    if "Italic" in style and style != "Italic":
        return style.replace("Italic", " Italic")
    return style


def english_names(base_family: str, style: str) -> dict[int, str]:
    """Build name entries using the same naming convention as upstream PlemolJP's edit_meta_data"""
    weight = weight_display(style)
    postscript = f"{base_family}-{weight}".replace(" ", "")
    full = f"{base_family} {weight}"
    if style in BASIC_STYLES:
        return {1: base_family, 2: weight, 4: full, 6: postscript}
    return {
        1: f"{base_family} {weight.split(' ')[0]}",
        2: "Italic" if "Italic" in style else "Regular",
        4: full,
        6: postscript,
        16: base_family,
        17: weight,
    }


def localized_family(base_family: str, region: str, label: str) -> str:
    """Replace the region token in the family name with the localized label"""
    return base_family.replace(f" {region}", f" {label}")


def set_name_table(
    font: TTFont,
    config: plemocjk_config.Config,
    region: str,
    base_family: str,
    style: str,
) -> None:
    name = font["name"]
    english = english_names(base_family, style)
    english[3] = f"{config.version};{base_family} {weight_display(style)}"

    keep: set[tuple[int, int, int, int]] = set()
    for name_id, value in english.items():
        for platform_id, plat_enc_id, lang_id in ((3, 1, 0x0409), (1, 0, 0)):
            name.setName(value, name_id, platform_id, plat_enc_id, lang_id)
            keep.add((name_id, platform_id, plat_enc_id, lang_id))

    # Localized family names (nameID 1 / 16)
    region_obj = config.regions[region]
    for locale, label in region_obj.localized_labels.items():
        lang_id = plemocjk_config.WINDOWS_LANG_IDS.get(locale)
        if lang_id is None:
            continue
        local_base = localized_family(base_family, region, label)
        local_english = english_names(local_base, style)
        for name_id in (1, 16):
            if name_id not in local_english:
                continue
            name.setName(local_english[name_id], name_id, 3, 1, lang_id)
            keep.add((name_id, 3, 1, lang_id))

    # Drop region-less names inherited from the upstream eng font
    name.names = [
        record
        for record in name.names
        if record.nameID not in NAME_IDS_TO_REWRITE
        or (record.nameID, record.platformID, record.platEncID, record.langID) in keep
    ]
    name.names.sort(key=lambda r: (r.platformID, r.platEncID, r.langID, r.nameID))


def set_meta_table(font: TTFont, config: plemocjk_config.Config, region: str) -> None:
    region_obj = config.regions[region]
    meta = table__m_e_t_a()
    meta.data = {"dlng": region_obj.meta_dlng, "slng": region_obj.meta_slng}
    font["meta"] = meta


def set_os2(font: TTFont, config: plemocjk_config.Config, region: str) -> None:
    os2 = font["OS/2"]
    if os2.version < 1:
        os2.version = 4
    range1 = 0
    range2 = 0
    for bit in config.regions[region].code_page_bits:
        if bit < 32:
            range1 |= 1 << bit
        else:
            range2 |= 1 << (bit - 32)
    os2.ulCodePageRange1 = range1
    os2.ulCodePageRange2 = range2
    # Force vertical metrics to use OS/2 typo* values
    os2.fsSelection |= USE_TYPO_METRICS


def add_hdmx(font: TTFont, config: plemocjk_config.Config, half_width: int) -> None:
    """Add hdmx to guarantee "2 half-width == 1 full-width" at the pixel level.

    hdmx[ppem][glyph] = cell_count * ceil(ppem / 2)
    half-width = ceil(ppem/2), full-width = 2 * half-width.
    """
    hmtx = font["hmtx"]
    glyph_order = font.getGlyphOrder()
    cells = {}
    for glyph_name in glyph_order:
        advance = hmtx.metrics[glyph_name][0]
        cells[glyph_name] = 0 if advance <= 0 else max(1, round(advance / half_width))

    table = font["hdmx"] if "hdmx" in font else None
    if table is None:
        from fontTools.ttLib import newTable

        table = newTable("hdmx")
        font["hdmx"] = table
    table.hdmx = {}
    for ppem in range(config.hdmx_ppem_min, config.hdmx_ppem_max + 1, 2):
        half_px = math.ceil(ppem / 2)
        widths = {}
        for glyph_name, cell_count in cells.items():
            width = cell_count * half_px
            if width > 255:
                width = 255
            widths[glyph_name] = width
        table.hdmx[ppem] = widths

    font["head"].flags |= HEAD_FLAG_INSTRUCTIONS_DEPEND_ON_PPEM


def apply(path: str, region: str, variant_tag: str, style: str) -> None:
    config = plemocjk_config.load()
    base_family = config.family_from_tag(variant_tag, region)
    wmode = plemocjk_config.width_mode_for_tag(variant_tag)

    font = TTFont(path, recalcBBoxes=False, recalcTimestamp=False)
    set_name_table(font, config, region, base_family, style)
    set_meta_table(font, config, region)
    set_os2(font, config, region)
    if wmode == "12":
        add_hdmx(font, config, config.half_width_12)
    elif wmode == "36":
        add_hdmx(font, config, config.half_width_36)
    font.save(path)
    font.close()
    print(
        f"metadata: {path} family='{base_family}' region={region} "
        f"hdmx={'no' if wmode == '35' else 'yes'}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(
            f"Usage: {sys.argv[0]} <font.ttf> <region> <variant_tag> <style>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    apply(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
