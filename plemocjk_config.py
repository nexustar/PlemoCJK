#!/usr/bin/env python3
"""build.ini の PlemoCJK 固有セクション ([regions] / [region.XX] / [build]) を読む。

prepare_cjk.py / fonttools_script.py / check_fonts.py / bundle 用スクリプトから
共通で使う。上流 PlemolJP のファイルへの変更を小さく保つために、
地域関連のロジックはできるだけこのモジュールに寄せている。
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# name テーブルで使う Windows の言語 ID
WINDOWS_LANG_IDS = {
    "en": 0x0409,
    "zh_CN": 0x0804,
    "zh_TW": 0x0404,
    "ja": 0x0411,
    "ko": 0x0412,
}

# 直立 8 ウェイト (CJK 側のソースに存在するウェイト)
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

# 上流 PlemolJP と同じ 16 スタイル (CJK 側スタイル, 英数字側スタイル)
STYLE_PAIRS = tuple(
    [(s, s) for s in UPRIGHT_STYLES]
    + [(s, f"{s}Italic" if s != "Regular" else "Italic") for s in UPRIGHT_STYLES]
)

ALL_STYLES = tuple(
    [s for s in UPRIGHT_STYLES] + [eng for _, eng in STYLE_PAIRS[len(UPRIGHT_STYLES) :]]
)

# バリアント名 -> (fontforge_script.py のオプション, 名前に入る修飾子のテンプレート)
# {R} は地域ラベルに置換される
VARIANT_TABLE = {
    "default": ("", "{R}"),
    "35": ("--35", "35{R}"),
    "Console": ("--console", "{R}Console"),
    "35Console": ("--console --35", "35{R}Console"),
    "ConsoleNF": ("--console --nerd-font", "{R}ConsoleNF"),
    "35ConsoleNF": ("--console --35 --nerd-font", "35{R}ConsoleNF"),
    "HS": ("--hidden-zenkaku-space", "{R}HS"),
    "35HS": ("--hidden-zenkaku-space --35", "35{R}HS"),
    "ConsoleHS": ("--hidden-zenkaku-space --console", "{R}ConsoleHS"),
    "35ConsoleHS": ("--hidden-zenkaku-space --console --35", "35{R}ConsoleHS"),
}


def parse_ranges(text: str) -> list[tuple[int, int]]:
    """"AC00-D7A3, 3130-318F" 形式を [(0xAC00, 0xD7A3), ...] にする"""
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
    """"SC:Text, TC:Bold" 形式を {("SC", "Text"), ("TC", "Bold")} にする"""
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
    settings: configparser.ConfigParser
    root: Path
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
    full_variants: list[str]
    ttc_order: list[str]
    hdmx_ppem_min: int
    hdmx_ppem_max: int

    def release_source_path(self, region: str, style: str) -> Path:
        """IBM 発布件のパス (再生成の対象かどうかに関わらず)"""
        return self.source_dir / self.region_source_font.replace(
            "{region}", region
        ).replace("{style}", style)

    def regenerated_path(self, region: str, style: str) -> Path:
        """母版から作り直したフォントのパス (regen_sc_text.py の出力)"""
        return self.source_dir / self.regenerated_font.replace(
            "{region}", region
        ).replace("{style}", style)

    def is_regenerated(self, region: str, style: str) -> bool:
        """REGENERATED_STYLES で発布件を差し替える指定になっているか"""
        return (region, style) in self.regenerated_styles

    def region_source_path(self, region: str, style: str) -> Path:
        """CJK 側の入力に使うフォント。再生成の指定があればそちらを返す"""
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
        """バリアント名と地域からフォント名の修飾子を作る (例: SCConsoleNF)"""
        return VARIANT_TABLE[variant][1].replace("{R}", region)

    def variant_options(self, variant: str) -> str:
        return VARIANT_TABLE[variant][0]

    def variant_from_tag(self, tag: str, region: str) -> str:
        """修飾子 (例: SCConsoleNF) からバリアント名を逆引きする"""
        for variant in VARIANT_TABLE:
            if self.variant_tag(variant, region) == tag:
                return variant
        raise KeyError(f"unknown variant tag {tag!r} for region {region!r}")

    def family_from_tag(self, tag: str, region: str) -> str:
        return self.family_name(self.variant_from_tag(tag, region), region)

    def family_name(self, variant: str, region: str) -> str:
        """表示用ファミリー名 (例: PlemoCJK35 SC Console NF)"""
        tag = self.variant_tag(variant, region)
        # 上流 PlemolJP と同じ組み立て規則:
        #   FONT_NAME + " " + 修飾子 (ただし " 35" は詰めて "35" にする)
        parts = []
        if tag.startswith("35"):
            parts.append("35")
            tag = tag[2:]
        parts.append(region)
        rest = tag[len(region) :]
        for marker in ("Console", "NF", "HS"):
            if rest.startswith(marker):
                parts.append(marker)
                rest = rest[len(marker) :]
        # Console の後ろに NF / HS が続く場合
        for marker in ("NF", "HS"):
            if rest.startswith(marker):
                parts.append(marker)
                rest = rest[len(marker) :]
        name = self.font_name
        if parts and parts[0] == "35":
            name += "35"
            parts = parts[1:]
        if parts:
            name += " " + " ".join(parts)
        return name


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
        settings=settings,
        root=root,
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
        full_variants=parse_list(settings.get("build", "FULL_VARIANTS")),
        ttc_order=parse_list(settings.get("build", "TTC_ORDER")),
        hdmx_ppem_min=settings.getint("build", "HDMX_PPEM_MIN"),
        hdmx_ppem_max=settings.getint("build", "HDMX_PPEM_MAX"),
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
                    for v in config.full_variants
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )
