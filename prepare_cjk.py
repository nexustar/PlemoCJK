#!/usr/bin/env python3
"""地域別の CJK 側入力フォントを作る (PlemoCJK)。

各地域の IBM Plex Sans を主体に、その地域に無いコードポイントだけを
他地域のフォントから補う (回退補入 / fallback fill)。出力は
source/prepared/PlemoCJK-{region}-{style}.ttf で、
fontforge_script.py が --region 指定時に JP_FONT の代わりに読む。

設計上の約束:

1. 既存グリフは絶対に上書きしない。主地域に存在するコードポイントは
   必ず主地域のグリフが使われる。
2. 補入順は build.ini の FALLBACK_{region} に従う。
   SC <- JP <- TC <- KR / TC <- SC <- JP <- KR /
   JP <- SC <- TC <- KR / KR <- JP <- SC <- TC
   どの地域も最終的に 4 地域のコードポイントの和集合になるので、
   4 つのサブフォントのカバレッジは完全に一致する。
   (ハングルが全地域に入るのはこの規則の帰結)
3. GSUB は主地域のものだけを残す。補入元の GSUB / GPOS は捨てる。
   漢字に locl は入れない (地域別サブフォントで出し分ける方針)。
4. build.ini の REGENERATED_STYLES に挙がった (地域, ウェイト) は
   IBM 発布件ではなく regen_sc_text.py が母版から作り直したものを読む。
   現状は SC の Text だけ (発布件は補間位置 425 で JP / TC より約 5% 細い)。
5. TrueType 命令は既定で落とす。理由は 2 つ。
   - ヒンティングは後段の ttfautohint が英数字側に付ける (上流 PlemolJP と同じ)
   - KR 原本は fpgm/prep/cvt を前提にした命令を持つため、補入先に
     そのまま持ち込むと壊れる。落とせば全地域でハングルのグリフが
     バイト単位で同一になり、TTC の glyf 共有が効く。

Usage:
    python3 prepare_cjk.py                          # 4 地域 x 8 ウェイト
    python3 prepare_cjk.py --regions SC --styles Regular
    python3 prepare_cjk.py --report                 # 補入内容の集計だけ出す
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

# 補入元から持ち込まないテーブル
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

# ヒンティングを落とすときに消すテーブル
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
    """グリフの TrueType 命令と関連テーブルを落とす"""
    glyf = font["glyf"]
    for name in font.getGlyphOrder():
        glyph = glyf[name]  # __getitem__ が expand() して .data を捨てる
        if glyph.isComposite():
            # コンポジットは program 属性の有無で WE_HAVE_INSTRUCTIONS が決まる
            if hasattr(glyph, "program"):
                del glyph.program
        elif glyph.numberOfContours > 0:
            # 単純グリフは compile() が program を必ず参照するので空にする
            glyph.program = ttProgram.Program()
            glyph.program.fromBytecode(b"")
        elif hasattr(glyph, "program"):
            del glyph.program
    for tag in HINTING_TABLES:
        if tag in font:
            del font[tag]
    # maxp のヒンティング関連の上限も 0 にする
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
    """補入元フォントを必要なコードポイントだけに絞る"""
    font = open_font(path)
    options = base_options(keep_hints)
    options.layout_features = []  # GSUB/GPOS の feature を一切残さない
    options.name_IDs = []
    options.name_languages = []
    options.drop_tables = list(set(options.drop_tables) | set(DROP_FROM_DONOR))
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=codepoints)
    subsetter.subset(font)
    return font


def load_primary(path: Path, keep_features: list[str], keep_hints: bool) -> TTFont:
    """主地域フォントを開き、不要な GSUB feature とそのグリフを落とす。

    GPOS は上流 fontforge_script.py がどのみち remove_lookups で消すので
    ここで落としておく (48,000 グリフ規模だと FontForge の処理が重くなるため)。
    vhea / vmtx も上流 fonttools_script.py の merge_fonts が削除しているので
    ここで落とす (補入したグリフの縦メトリクスを作る意味が無い)。
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
    """補入元の全グリフを主フォントに追加し、cmap 用の対応表を返す。

    グリフ名は衝突を避けるため接尾辞を付ける。コンポジットの参照も張り替える。
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
                # .notdef を参照するコンポジットは現実には無いが保険
                component.glyphName = rename.get(
                    component.glyphName, component.glyphName
                )
        primary_glyf.glyphs[new_name] = glyph
        primary_hmtx.metrics[new_name] = donor_hmtx.metrics[name]

    new_order = order + added
    primary.setGlyphOrder(new_order)
    primary_glyf.glyphOrder = new_order
    # getGlyphID のキャッシュを捨てる
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
    """Unicode cmap サブテーブルを mapping で作り直す。

    Mac の legacy サブテーブル等は捨てる。
    format 4 は length が uint16 なので、補入でグリフ ID が不連続になると
    64KB を超えて書けなくなる。その場合は format 12 のみにする
    (この中間ファイルを読むのは FontForge だけなので問題ない)。
    """
    bmp = {cp: name for cp, name in mapping.items() if cp <= 0xFFFF}

    tables = [
        make_cmap_subtable(3, 10, 12, mapping),
        make_cmap_subtable(0, 4, 12, mapping),
    ]

    # format 4 が収まるなら互換性のために付けておく
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


# CJK 互換漢字のブロック (正規分解が単独の統合漢字になるもの)
COMPAT_IDEOGRAPH_RANGES = ((0xF900, 0xFAFF), (0x2F800, 0x2FA1D))


def compat_ideograph_aliases(mapping: dict[int, str]) -> dict[int, str]:
    """CJK 互換漢字を正規等価な統合漢字のグリフに向けるエイリアスを返す。

    IBM Plex Sans はこのブロックのグリフを持たないので、そのままだと
    KS X 1001 の 268 字 (と GBK の一部) が欠ける。Unicode 上はこれらは
    統合漢字との正規等価 (singleton decomposition) なので、同じグリフを
    指させれば意味的に正しい。新しいグリフは 1 つも増えない。
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
    """1 つのグリフを複数のコードポイントが共有している状態を解消する。

    FontForge はこれを altuni として読むが、上流 fontforge_script.py の
    delete_duplicate_glyphs / materialize_altuni_glyphs は
    「別名の片方が英数字側にもある」ケースを取りこぼし、
    共有グリフごと clear() してもう片方のコードポイントまで落としてしまう。

    実測では IBM Plex Sans TC の Big5/HKSCS 別名 (4,900 個強) の一部が
    Powerline の PUA (U+E0A0-E0D4) と衝突し、U+542F や U+FF5E など 35 個の
    コードポイントが TC サブフォントから消えていた。

    コードポイントごとに実体を 1 つ持たせれば altuni が発生しないので、
    この問題は原理的に起きなくなる。グリフのバイト列は同一なので
    TTC の glyf 共有には影響しない。
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
        # 一番小さいコードポイントが元のグリフを使い、残りは複製を持つ
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
    """ビルドログとテンポラリファイル名のために分かりやすい名前を入れる。

    最終的な name テーブルは fontforge_script.py / fonttools_script.py が作る。
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
    """1 地域 1 ウェイトの CJK 側入力フォントを作る"""
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
            if cp in mapping:  # 念のため: 既存グリフは絶対に上書きしない
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

    hangul = config.hangul_codepoints()

    def is_regenerated(region: str, style: str) -> bool:
        # --font-template を明示した場合はそのテンプレートが全地域に効く
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
