#!/usr/bin/env python3
"""Read PlemoCJK-specific sections ([regions] / [region.XX] / [build]) from build.ini.

Shared by prepare_cjk.py, fonttools_script.py, check_fonts.py, and bundle scripts.
Region-related logic is concentrated in this module to minimize changes to upstream
PlemolJP files.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Windows language IDs used in the name table
WINDOWS_LANG_IDS = {
    "en": 0x0409,
    "zh_CN": 0x0804,
    "zh_TW": 0x0404,
    "ja": 0x0411,
    "ko": 0x0412,
}

# 8 upright weights (weights present in CJK source fonts)
UPRIGHT_STYLES = (
    "Thin",
    "ExtraLight",
    "Light",
    "Regular",
    "Text",
    "Medium",
    "SemiBold",
    "Bold",
)

ALL_STYLES = tuple(
    list(UPRIGHT_STYLES)
    + [f"{s}Italic" if s != "Regular" else "Italic" for s in UPRIGHT_STYLES]
)

@dataclass(frozen=True)
class Variant:
    """A build variant defined by explicit feature flags.

    Behaviour comes only from the flags below. `label` is output-only: it feeds
    the family name and the file tag, and is never parsed back into behaviour.
    It defaults to `key`; the unmarked `default` variant sets it to "".
    """

    key: str                        # registry id, used by build.ini / make.sh
    label: str | None = None        # name suffix; defaults to key, "" for default
    width_mode: str = "12"          # "12" | "35" | "36"
    console: bool = False
    nerd_font: bool = False
    hidden_zenkaku_space: bool = False

    def __post_init__(self) -> None:
        if self.label is None:
            object.__setattr__(self, "label", self.key)

    def flags(self) -> list[str]:
        """fontforge_script.py options for this variant."""
        out: list[str] = []
        if self.hidden_zenkaku_space:
            out.append("--hidden-zenkaku-space")
        if self.console:
            out.append("--console")
        if self.nerd_font:
            out.append("--nerd-font")
        if self.width_mode == "35":
            out.append("--35")
        elif self.width_mode == "36":
            out.append("--36")
        return out

    def tag(self, region: str = "") -> str:
        """File/name tag: label + region, e.g. 'TermSC', 'Term', or 'SC'."""
        return f"{self.label}{region}"

    def family_name(self, font_name: str, region: str) -> str:
        """Display family name, e.g. 'PlemoCJK Term SC' or 'PlemoCJK SC'."""
        parts = [p for p in (self.label, region) if p]
        return " ".join([font_name, *parts]) if parts else font_name


# Shipped variants. Add a row to ship another one; nothing parses the name.
VARIANTS: dict[str, Variant] = {
    v.key: v
    for v in [
        Variant("default", label="", hidden_zenkaku_space=True),
        Variant("Term", width_mode="36", console=True, nerd_font=True),
        Variant("Natural", width_mode="35", hidden_zenkaku_space=True),
        # Planned (verified to build; enable when shipping):
        # Variant("Wide", width_mode="36", hidden_zenkaku_space=True),
    ]
}


_REGIONS = frozenset(("SC", "TC", "JP", "KR"))
_WIDTH_PREFIXES = ("36", "35")


def hyphenate_tag(tag: str) -> str:
    """Insert hyphens between logical components of a variant tag for filenames.

    TermSC -> Term-SC, 35ConsoleSC -> 35-Console-SC, SC -> SC, "" -> ""
    Internal tags stay hyphen-free (intermediate files depend on that);
    this function is used only when constructing final output filenames.
    """
    if not tag:
        return tag
    parts: list[str] = []
    rest = tag
    for p in _WIDTH_PREFIXES:
        if rest.startswith(p):
            parts.append(p)
            rest = rest[len(p):]
            break
    region = ""
    for r in _REGIONS:
        if rest.endswith(r):
            region = r
            rest = rest[:-len(r)]
            break
    if rest:
        parts.append(rest)
    if region:
        parts.append(region)
    return "-".join(parts)


def width_mode_for_variant(variant: str) -> str:
    """Return '12' | '35' | '36' for a variant key (no name parsing)."""
    return VARIANTS[variant].width_mode


def width_mode_for_tag(tag: str) -> str:
    """Return '12' | '35' | '36' for a file tag (label + optional region).

    Matches the tag against the registry's own tags, so it stays correct for
    editorial labels like 'Natural'/'Wide' that carry no width marker. Prefer
    width_mode_for_variant in the build path; this is only for tools that have
    just an output filename to work from.
    """
    for v in VARIANTS.values():
        if tag == v.tag() or any(tag == v.tag(r) for r in _REGIONS):
            return v.width_mode
    return "12"


def parse_ranges(text: str) -> list[tuple[int, int]]:
    """Parse "AC00-D7A3, 3130-318F" format into [(0xAC00, 0xD7A3), ...]"""
    result = []
    for item in text.replace("\n", ",").split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            start, end = item.split("-", 1)
            result.append((int(start, 16), int(end, 16)))
        else:
            value = int(item, 16)
            result.append((value, value))
    return result


def expand_ranges(ranges: list[tuple[int, int]]) -> set[int]:
    out: set[int] = set()
    for start, end in ranges:
        out.update(range(start, end + 1))
    return out


def parse_list(text: str) -> list[str]:
    return [x.strip() for x in text.replace("\n", ",").split(",") if x.strip()]


def parse_int_list(text: str) -> list[int]:
    return [int(x, 0) for x in parse_list(text)]


def parse_pair_set(text: str) -> set[tuple[str, str]]:
    """Parse "SC:Text, TC:Bold" format into {("SC", "Text"), ("TC", "Bold")}"""
    pairs = set()
    for item in parse_list(text):
        left, separator, right = item.partition(":")
        if not separator:
            raise ValueError(f"expected 'region:style', got {item!r}")
        pairs.add((left.strip(), right.strip()))
    return pairs


@dataclass
class Region:
    name: str
    label: str
    fallback: list[str]
    meta_dlng: str
    meta_slng: str
    code_page_bits: list[int]
    localized_labels: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    font_name: str
    version: str
    source_dir: Path
    build_dir: Path
    region_source_font: str
    regenerated_font: str
    regenerated_styles: set[tuple[str, str]]
    prepared_font: str
    regions: dict[str, Region]
    exclude_codepoints: set[int]
    alias_compat_ideographs: bool
    gsub_keep_features: list[str]
    hangul_ranges: list[tuple[int, int]]
    half_width_hangul_ranges: list[tuple[int, int]]
    default_variants: list[str]
    ttc_order: list[str]
    hdmx_ppem_min: int
    hdmx_ppem_max: int
    half_width_12: int
    half_width_36: int

    def release_source_path(self, region: str, style: str) -> Path:
        """Path to the IBM release font (regardless of regeneration status)"""
        return self.source_dir / self.region_source_font.replace(
            "{region}", region
        ).replace("{style}", style)

    def regenerated_path(self, region: str, style: str) -> Path:
        """Path to font regenerated from the Glyphs master (regen_sc_text.py output)"""
        return self.source_dir / self.regenerated_font.replace(
            "{region}", region
        ).replace("{style}", style)

    def is_regenerated(self, region: str, style: str) -> bool:
        """Whether the release font is replaced via REGENERATED_STYLES"""
        return (region, style) in self.regenerated_styles

    def region_source_path(self, region: str, style: str) -> Path:
        """Font used as CJK input; returns the regenerated version if specified"""
        if self.is_regenerated(region, style):
            return self.regenerated_path(region, style)
        return self.release_source_path(region, style)

    def prepared_path(self, region: str, style: str) -> Path:
        return self.source_dir / self.prepared_font.replace("{region}", region).replace(
            "{style}", style
        )

    def hangul_codepoints(self) -> set[int]:
        return expand_ranges(self.hangul_ranges)

    def half_width_hangul_codepoints(self) -> set[int]:
        return expand_ranges(self.half_width_hangul_ranges)

    def variant_tag(self, variant: str, region: str) -> str:
        """File/name tag for a variant key + region (e.g. 'TermSC', 'SC')."""
        return VARIANTS[variant].tag(region)

    def variant_options(self, variant: str) -> str:
        return " ".join(VARIANTS[variant].flags())

    def variant_from_tag(self, tag: str, region: str) -> str:
        """Registry lookup: which variant key produces this tag for this region."""
        for key, variant in VARIANTS.items():
            if variant.tag(region) == tag:
                return key
        raise KeyError(f"unknown variant tag {tag!r} for region {region!r}")

    def family_from_tag(self, tag: str, region: str) -> str:
        return self.family_name(self.variant_from_tag(tag, region), region)

    def family_name(self, variant: str, region: str) -> str:
        """Display family name (e.g. 'PlemoCJK Term SC')."""
        return VARIANTS[variant].family_name(self.font_name, region)


def load(root: Path | None = None) -> Config:
    root = root or ROOT
    settings = configparser.ConfigParser()
    read = settings.read(root / "build.ini", encoding="utf-8")
    if not read:
        raise RuntimeError(f"build.ini not found under {root}")

    region_names = parse_list(settings.get("regions", "REGIONS"))
    regions: dict[str, Region] = {}
    for name in region_names:
        section = f"region.{name}"
        localized = {}
        for item in parse_list(settings.get(section, "LOCALIZED_LABELS", fallback="")):
            key, _, value = item.partition(":")
            if value:
                localized[key.strip()] = value.strip()
        regions[name] = Region(
            name=name,
            label=settings.get(section, "LABEL", fallback=name),
            fallback=parse_list(settings.get("regions", f"FALLBACK_{name}")),
            meta_dlng=settings.get(section, "META_DLNG"),
            meta_slng=settings.get(section, "META_SLNG"),
            code_page_bits=parse_int_list(settings.get(section, "CODE_PAGE_BITS")),
            localized_labels=localized,
        )

    source_dir = root / settings.get("DEFAULT", "SOURCE_FONTS_DIR")
    build_dir = root / settings.get("DEFAULT", "BUILD_FONTS_DIR")

    return Config(
        font_name=settings.get("DEFAULT", "FONT_NAME"),
        version=settings.get("DEFAULT", "VERSION"),
        source_dir=source_dir,
        build_dir=build_dir,
        region_source_font=settings.get("regions", "REGION_SOURCE_FONT"),
        regenerated_font=settings.get(
            "regions", "REGENERATED_FONT", fallback="regenerated/{region}-{style}.ttf"
        ),
        regenerated_styles=parse_pair_set(
            settings.get("regions", "REGENERATED_STYLES", fallback="")
        ),
        prepared_font=settings.get("regions", "PREPARED_FONT"),
        regions=regions,
        exclude_codepoints=set(
            parse_int_list(settings.get("regions", "EXCLUDE_CODEPOINTS", fallback=""))
        ),
        alias_compat_ideographs=settings.getboolean(
            "regions", "ALIAS_COMPAT_IDEOGRAPHS", fallback=True
        ),
        gsub_keep_features=parse_list(
            settings.get("regions", "GSUB_KEEP_FEATURES", fallback="")
        ),
        hangul_ranges=parse_ranges(settings.get("regions", "HANGUL_RANGES")),
        half_width_hangul_ranges=parse_ranges(
            settings.get("regions", "HALF_WIDTH_HANGUL_RANGES")
        ),
        default_variants=parse_list(settings.get("build", "DEFAULT_VARIANTS")),
        ttc_order=parse_list(settings.get("build", "TTC_ORDER")),
        hdmx_ppem_min=settings.getint("build", "HDMX_PPEM_MIN"),
        hdmx_ppem_max=settings.getint("build", "HDMX_PPEM_MAX"),
        half_width_12=settings.getint("DEFAULT", "HALF_WIDTH_12"),
        half_width_36=settings.getint("DEFAULT", "HALF_WIDTH_36"),
    )


if __name__ == "__main__":
    import json

    config = load()
    print(
        json.dumps(
            {
                "font_name": config.font_name,
                "regions": list(config.regions),
                "fallback": {r.name: r.fallback for r in config.regions.values()},
                "default_variants": config.default_variants,
                "families": {
                    v: {
                        r: config.family_name(v, r)
                        for r in ("SC", "TC", "JP", "KR")
                    }
                    for v in config.default_variants
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )
