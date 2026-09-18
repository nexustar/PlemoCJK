#!fontforge --lang=py -script

# 2つのフォントを合成する

import configparser
import math
import os
import shutil
import sys
import uuid
from decimal import ROUND_HALF_UP, Decimal

import fontforge
import psMat

# iniファイルを読み込む
settings = configparser.ConfigParser()
settings.read("build.ini", encoding="utf-8")

VERSION = settings.get("DEFAULT", "VERSION")
FONT_NAME = settings.get("DEFAULT", "FONT_NAME")
JP_FONT = settings.get("DEFAULT", "JP_FONT")
# PlemoCJK: per-region CJK input font built by prepare_cjk.py, used with --region
PREPARED_FONT = settings.get("regions", "PREPARED_FONT")
HALF_WIDTH_HANGUL_RANGES = settings.get("regions", "HALF_WIDTH_HANGUL_RANGES")
ENG_FONT = settings.get("DEFAULT", "ENG_FONT")
HACK_FONT = settings.get("DEFAULT", "HACK_FONT")
SOURCE_FONTS_DIR = settings.get("DEFAULT", "SOURCE_FONTS_DIR")
BUILD_FONTS_DIR = settings.get("DEFAULT", "BUILD_FONTS_DIR")
VENDER_NAME = settings.get("DEFAULT", "VENDER_NAME")
FONTFORGE_PREFIX = settings.get("DEFAULT", "FONTFORGE_PREFIX")
IDEOGRAPHIC_SPACE = settings.get("DEFAULT", "IDEOGRAPHIC_SPACE")
ADJUST_R = settings.get("DEFAULT", "ADJUST_R")
CONSOLE_STR = settings.get("DEFAULT", "CONSOLE_STR")
WIDTH_35_STR = settings.get("DEFAULT", "WIDTH_35_STR")
INVISIBLE_ZENKAKU_SPACE_STR = settings.get("DEFAULT", "INVISIBLE_ZENKAKU_SPACE_STR")
NERD_FONTS_STR = settings.get("DEFAULT", "NERD_FONTS_STR")
EM_ASCENT = int(settings.get("DEFAULT", "EM_ASCENT"))
EM_DESCENT = int(settings.get("DEFAULT", "EM_DESCENT"))
TYPO_ASCENT = int(settings.get("DEFAULT", "TYPO_ASCENT"))
TYPO_DESCENT = int(settings.get("DEFAULT", "TYPO_DESCENT"))
WIN_ASCENT = int(settings.get("DEFAULT", "WIN_ASCENT"))
WIN_DESCENT = int(settings.get("DEFAULT", "WIN_DESCENT"))
HALF_WIDTH_12 = int(settings.get("DEFAULT", "HALF_WIDTH_12"))
FULL_WIDTH_35 = int(settings.get("DEFAULT", "FULL_WIDTH_35"))
FULL_WIDTH_36 = int(settings.get("DEFAULT", "FULL_WIDTH_36"))
WIDTH_36_STR = settings.get("DEFAULT", "WIDTH_36_STR")
ITALIC_ANGLE = int(settings.get("DEFAULT", "ITALIC_ANGLE"))

COPYRIGHT = """[IBM Plex]
Copyright (c) 2017 IBM Corp. https://github.com/IBM/plex

[Hack]
Copyright 2018 Source Foundry Authors https://github.com/source-foundry/Hack

[Nerd Fonts]
Copyright (c) 2014, Ryan L McIntyre https://ryanlmcintyre.com

[PlemolJP]
Copyright (c) 2021, Yuko Otawara

[PlemoCJK]
Copyright (c) 2025, PlemoCJK Authors https://github.com/nexustar/PlemoCJK
"""  # noqa: E501

options = {}
nerd_font = None


# List of styles to generate (CJK-side style, alphanumeric-side style, output style)
STYLE_TABLE = (
    ("Regular", "Regular", "Regular"),
    ("Bold", "Bold", "Bold"),
    ("Thin", "Thin", "Thin"),
    ("ExtraLight", "ExtraLight", "ExtraLight"),
    ("Light", "Light", "Light"),
    ("Text", "Text", "Text"),
    ("Medium", "Medium", "Medium"),
    ("SemiBold", "SemiBold", "SemiBold"),
    ("Regular", "Italic", "Italic"),
    ("Bold", "BoldItalic", "BoldItalic"),
    ("Thin", "ThinItalic", "ThinItalic"),
    ("ExtraLight", "ExtraLightItalic", "ExtraLightItalic"),
    ("Light", "LightItalic", "LightItalic"),
    ("Text", "TextItalic", "TextItalic"),
    ("Medium", "MediumItalic", "MediumItalic"),
    ("SemiBold", "SemiBoldItalic", "SemiBoldItalic"),
)
ALL_STYLES = tuple(style for _, _, style in STYLE_TABLE)


def parse_hex_ranges(text):
    """Parse "FFA1-FFDC, 3000" format into [(start, end), ...]"""
    ranges = []
    for item in text.replace("\n", ",").split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            start, end = item.split("-", 1)
            ranges.append((int(start, 16), int(end, 16)))
        else:
            value = int(item, 16)
            ranges.append((value, value))
    return ranges


HALF_WIDTH_HANGUL = parse_hex_ranges(HALF_WIDTH_HANGUL_RANGES)


def is_half_width_hangul(unicode_value):
    """Exclude half-width Hangul Jamo (U+FFA1-FFDC) from full-width conversion"""
    return any(start <= unicode_value <= end for start, end in HALF_WIDTH_HANGUL)


def main():
    # オプション判定
    get_options()
    if options.get("unknown-option"):
        usage()
        return

    # buildディレクトリを作成する
    if os.path.exists(BUILD_FONTS_DIR) and not options.get("do-not-delete-build-dir"):
        shutil.rmtree(BUILD_FONTS_DIR)
        os.mkdir(BUILD_FONTS_DIR)
    if not os.path.exists(BUILD_FONTS_DIR):
        os.mkdir(BUILD_FONTS_DIR)

    styles = options.get("styles")
    if styles is None and options.get("debug"):
        # デバッグモードでは Regular のみ生成する
        styles = ["Regular"]

    for jp_style, eng_style, merged_style in STYLE_TABLE:
        if styles is not None and merged_style not in styles:
            continue
        generate_font(
            jp_style=jp_style,
            eng_style=eng_style,
            merged_style=merged_style,
        )


def usage():
    print(
        f"Usage: {sys.argv[0]} "
        "[--hidden-zenkaku-space] [--35] [--36] [--console] [--nerd-font] "
        "[--variant-name TAG] "
        "[--styles Regular,Bold,...] [--region SC|TC|JP|KR] [--eng-only]"
    )


def get_options():
    """オプションを取得する"""

    global options

    # オプションなしの場合は何もしない
    if len(sys.argv) == 1:
        return

    skip_next = False
    for index, arg in enumerate(sys.argv[1:], start=1):
        if skip_next:
            skip_next = False
            continue
        # オプション判定
        if arg == "--do-not-delete-build-dir":
            options["do-not-delete-build-dir"] = True
        elif arg == "--debug":
            options["debug"] = True
        # 生成するスタイルを絞る (カンマ区切り)
        elif arg == "--styles":
            if index + 1 >= len(sys.argv):
                options["unknown-option"] = True
                return
            styles = [s.strip() for s in sys.argv[index + 1].split(",") if s.strip()]
            unknown = [s for s in styles if s not in ALL_STYLES]
            if not styles or unknown:
                print(f"ERROR: unknown style(s): {', '.join(unknown)}")
                print(f"  available: {', '.join(ALL_STYLES)}")
                options["unknown-option"] = True
                return
            options["styles"] = styles
            skip_next = True
        elif arg == "--hidden-zenkaku-space":
            options["hidden-zenkaku-space"] = True
        elif arg == "--35":
            options["35"] = True
        elif arg == "--36":
            options["36"] = True
        elif arg == "--console":
            options["console"] = True
        elif arg == "--nerd-font":
            options["nerd-font"] = True
        elif arg == "--region":
            if index + 1 >= len(sys.argv):
                options["unknown-option"] = True
                return
            options["region"] = sys.argv[index + 1]
            skip_next = True
        elif arg == "--eng-only":
            options["eng-only"] = True
        elif arg == "--variant-name":
            if index + 1 >= len(sys.argv):
                options["unknown-option"] = True
                return
            options["variant-name"] = sys.argv[index + 1]
            skip_next = True
        else:
            options["unknown-option"] = True
            return


def generate_font(jp_style, eng_style, merged_style):
    print(f"=== Generate {merged_style} ===")

    # 合成するフォントを開く
    jp_font, eng_font = open_fonts(jp_style, eng_style)

    # フォントのEMを揃える
    adjust_em(eng_font)

    # Hack フォントをマージする
    merge_hack(jp_font, eng_font, merged_style)

    if options.get("console"):
        # East Asian Ambiguous Width 文字の半角化
        eaaw_width_to_half(jp_font)
        # コンソール用グリフを追加する
        add_console_glyphs(eng_font)

    if not options.get("console"):
        delete_not_console_glyphs(eng_font)

    # 重複するグリフを削除する
    jp_font = delete_duplicate_glyphs(jp_font, eng_font)

    # いくつかのグリフ形状に調整を加える
    adjust_some_glyph(jp_font, eng_font, merged_style)

    # 日本語グリフの斜体を生成する
    if "Italic" in merged_style:
        transform_italic_glyphs(jp_font)

    # Make alphabetic scripts (Greek/Cyrillic/IPA) half-width before normalizing
    adjust_letter_script_width(jp_font)

    # 半角幅か全角幅になるように変換する
    set_width_600_or_1000(jp_font)

    if options.get("36"):
        adjust_width_35_eng(eng_font)
        adjust_width_36_jp(jp_font)
    elif options.get("35"):
        # eng_fontを3:5幅にする
        adjust_width_35_eng(eng_font)
        # jp_fontを3:5幅にする
        adjust_width_35_jp(jp_font)
    else:
        # 1:2 幅にする
        transform_half_width(jp_font, eng_font)
        # 規定の幅からはみ出したグリフサイズを縮小する
        down_scale_redundant_size_glyph(eng_font)

    # GPOSテーブルを削除する
    remove_lookups(jp_font, remove_gsub=False, remove_gpos=True)

    # fit block elements to the line height (all variants)
    fit_block_line_height(eng_font)
    if not options.get("console"):
        # box drawing to full width
        make_box_drawing_full_width(eng_font, jp_font)
        # block elements to full width
        make_block_elements_full_width(eng_font, jp_font[0x3042].width)
        # shades ░▒▓: Hack squares, doubled to fill the full cell
        apply_shade_blocks(eng_font, merged_style, jp_font[0x3042].width, doubled=True)
    else:
        # console: half-width shades
        apply_shade_blocks(eng_font, merged_style, eng_font[0x0030].width, doubled=False)

    # 全角スペースを可視化する
    if not options.get("hidden-zenkaku-space"):
        visualize_zenkaku_space(jp_font)

    # Nerd Fontのグリフを追加する
    if options.get("nerd-font"):
        add_nerd_font_glyphs(jp_font, eng_font)

    # オプション毎の修飾子を追加する
    if options.get("variant-name") is not None:
        # PlemoCJK: caller-specified name overrides atomic-flag-based naming
        variant = options["variant-name"]
    else:
        if options.get("36"):
            variant = f"{WIDTH_36_STR} "
        elif options.get("35"):
            variant = f"{WIDTH_35_STR} "
        else:
            variant = ""
        # PlemoCJK: region modifier goes right after 35 (e.g. PlemoCJK35 SC Console NF)
        if options.get("region"):
            variant += f"{options['region']} "
        variant += f"{CONSOLE_STR} " if options.get("console") else ""
        variant += (
            INVISIBLE_ZENKAKU_SPACE_STR if options.get("hidden-zenkaku-space") else ""
        )
        variant += NERD_FONTS_STR if options.get("nerd-font") else ""
        variant = variant.strip()

    # macOSでのpostテーブルの使用性エラー対策
    # 重複するグリフ名を持つグリフをリネームする
    delete_glyphs_with_duplicate_glyph_names(eng_font)
    delete_glyphs_with_duplicate_glyph_names(jp_font)

    # メタデータを編集する
    cap_height = int(
        Decimal(str(eng_font[0x0048].boundingBox()[3])).quantize(
            Decimal("0"), ROUND_HALF_UP
        )
    )
    x_height = int(
        Decimal(str(eng_font[0x0078].boundingBox()[3])).quantize(
            Decimal("0"), ROUND_HALF_UP
        )
    )
    edit_meta_data(eng_font, merged_style, variant, cap_height, x_height)
    edit_meta_data(jp_font, merged_style, variant, cap_height, x_height)

    # ttfファイルに保存
    # ヒンティングが残っていると不具合に繋がりがちなので外す。
    # ヒンティングはあとで ttfautohint で行う。
    # flags=("no-hints", "omit-instructions") を使うとヒンティングだけでなく GPOS や GSUB も削除されてしまうので使わない
    font_name = f"{FONT_NAME}{variant}".replace(" ", "")
    # PlemoCJK: the alphanumeric side is region-independent, so it is built once
    # via --eng-only and reused across all 4 regions (byte-identical output).
    # When --region is specified, skip writing the alphanumeric side (it is still
    # built in memory because the CJK-side conversion needs it).
    if not options.get("region"):
        eng_font.generate(
            f"{BUILD_FONTS_DIR}/{FONTFORGE_PREFIX}{font_name}-{merged_style}-eng.ttf",
        )
    if not options.get("eng-only"):
        jp_font.generate(
            f"{BUILD_FONTS_DIR}/{FONTFORGE_PREFIX}{font_name}-{merged_style}-jp.ttf",
        )

    # ttfを閉じる
    jp_font.close()
    eng_font.close()


def cjk_font_path(jp_style: str) -> str:
    """Return the path to the CJK-side input font.

    PlemoCJK: when --region is given, use the per-region font built by prepare_cjk.py.
    Without a region, fall back to IBM Plex Sans JP as in upstream PlemolJP.
    """
    region = options.get("region")
    if region:
        return (
            SOURCE_FONTS_DIR
            + "/"
            + PREPARED_FONT.replace("{region}", region).replace("{style}", jp_style)
        )
    return SOURCE_FONTS_DIR + "/" + JP_FONT.replace("{style}", jp_style)


def open_fonts(jp_style: str, eng_style: str):
    """フォントを開く"""
    jp_font = fontforge.open(cjk_font_path(jp_style))
    eng_font = fontforge.open(
        SOURCE_FONTS_DIR + "/" + ENG_FONT.replace("{style}", eng_style)
    )

    # フォント参照を解除する
    for glyph in jp_font.glyphs():
        if glyph.isWorthOutputting():
            jp_font.selection.select(("more", None), glyph)
    jp_font.unlinkReferences()
    for glyph in eng_font.glyphs():
        if glyph.isWorthOutputting():
            eng_font.selection.select(("more", None), glyph)
    eng_font.unlinkReferences()
    jp_font.selection.none()
    eng_font.selection.none()

    return jp_font, eng_font


def adjust_some_glyph(jp_font, eng_font, style="Regular"):
    """いくつかのグリフ形状に調整を加える"""
    eng_glyph_width = eng_font[0x0020].width
    full_width = jp_font[0x3042].width
    if options.get("35") or options.get("36"):
        half_width = eng_glyph_width
    else:
        half_width = int(full_width / 2)

    # クォーテーションの拡大
    eng_font.selection.select(("unicode", None), 0x0060)
    for glyph in eng_font.selection.byGlyphs:
        glyph.transform(psMat.rotate(math.radians(-25)))
        glyph.transform(psMat.scale(1.08, 1.2))
        glyph.transform(psMat.rotate(math.radians(33)))
        glyph.transform(psMat.translate(110, -135))
        glyph.width = eng_glyph_width
    eng_font.selection.select(("unicode", None), 0x0027)
    eng_font.selection.select(("unicode", "more"), 0x0022)
    for glyph in eng_font.selection.byGlyphs:
        glyph.transform(psMat.scale(1.09, 1.06))
        glyph.transform(psMat.translate((eng_glyph_width - glyph.width) / 2, 0))
        glyph.width = eng_glyph_width
    # ; : , . の拡大
    eng_font.selection.select(("unicode", None), 0x003A)
    eng_font.selection.select(("unicode", "more"), 0x003B)
    eng_font.selection.select(("unicode", "more"), 0x002C)
    eng_font.selection.select(("unicode", "more"), 0x002E)
    for glyph in eng_font.selection.byGlyphs:
        glyph.transform(psMat.scale(1.08, 1.08))
        glyph.transform(psMat.translate((eng_glyph_width - glyph.width) / 2, 0))
        glyph.width = eng_glyph_width
    # Eclipse Pleiades 半角スペース記号 (U+1d1c) 対策
    eng_font.selection.select(("unicode", None), 0x054D)
    eng_font.copy()
    eng_font.selection.select(("unicode", None), 0x1D1C)
    eng_font.paste()
    for glyph in eng_font.selection.byGlyphs:
        glyph.transform(psMat.scale(0.85, 0.6))
        glyph.transform(psMat.translate((eng_glyph_width - glyph.width) / 2, 0))
        glyph.width = eng_glyph_width

    # 全角括弧の開きを広くする
    for glyph_name in [0xFF08, 0xFF3B, 0xFF5B]:
        glyph = jp_font[glyph_name]
        glyph.transform(psMat.translate(-180, 0))
        glyph.width = full_width
    for glyph_name in [0xFF09, 0xFF3D, 0xFF5D]:
        glyph = jp_font[glyph_name]
        glyph.transform(psMat.translate(180, 0))
        glyph.width = full_width
    # PlemoCJK: quotes U+2018/2019/201C/201D are not forced full-width here.
    # They come half-width from IBM Plex Mono for every region (they are no
    # longer in delete_not_console_glyphs).

    # Cent Sign, Pound Sign, Yen Sign は半角記号に IBM Plex Sans JP を使用するため半角にする
    jp_font.selection.select(("unicode", None), 0x00A2)
    jp_font.selection.select(("unicode", "more"), 0x00A3)
    jp_font.selection.select(("unicode", "more"), 0x00A5)
    for glyph in jp_font.selection.byGlyphs:
        x_scale = half_width / glyph.width
        if x_scale < 1:
            glyph.transform(psMat.scale(x_scale, 1))
        # 後から英語フォントと同じ幅にするために一旦500幅として扱う
        glyph.transform(psMat.translate((500 - glyph.width) / 2, 0))
        glyph.width = 500

    # 空白記号 (U+2423) は、プログラムなどの空白を文書上で表すため半角にする
    jp_font.selection.select(("unicode", None), 0x2423)
    for glyph in jp_font.selection.byGlyphs:
        x_scale = half_width / glyph.width
        if x_scale < 1:
            glyph.transform(psMat.scale(x_scale, 1))
        # 後から英語フォントと同じ幅にするために一旦500幅として扱う
        glyph.transform(psMat.translate((500 - glyph.width) / 2, 0))
        glyph.width = 500

        # 特定の点だけ +75 上に移動
        layer = glyph.foreground
        move_indices = {2, 3, 6, 7}
        for contour in layer:
            for i, point in enumerate(contour):
                if i in move_indices:
                    point.y += 100
        glyph.foreground = layer  # 書き戻し必須

    # r グリフの調整
    if "Italic" not in style:
        eng_font[0x0072].clear()
        eng_font[0x0155].clear()
        eng_font[0x0157].clear()
        eng_font[0x0159].clear()
        eng_font.mergeFonts(f"{SOURCE_FONTS_DIR}/" + ADJUST_R.replace("{style}", style))

    # 矢印記号の読みづらさ対策
    for uni in [*range(0x21CD, 0x21CF + 1), 0x21D0, 0x21D2, 0x21D4, 0x21DA, 0x21DB]:
        eng_font.selection.select(("unicode", None), uni)
        for glyph in eng_font.selection.byGlyphs:
            scale_glyph_from_center(glyph, 1, 1.3)
    for uni in [0x21D1, 0x21D3]:
        eng_font.selection.select(("unicode", None), uni)
        for glyph in eng_font.selection.byGlyphs:
            scale_glyph_from_center(glyph, 1.3, 1)
    for uni in range(0x21D6, 0x21D9 + 1):
        eng_font.selection.select(("unicode", None), uni)
        for glyph in eng_font.selection.byGlyphs:
            scale_glyph_from_center(glyph, 1.3, 1.3)

    # 選択解除
    jp_font.selection.none()
    eng_font.selection.none()


def adjust_em(font):
    """フォントのEMを揃える"""
    font.em = EM_ASCENT + EM_DESCENT


def delete_duplicate_glyphs(jp_font, eng_font):
    """jp_fontとeng_fontのグリフを比較し、重複するグリフを削除する"""

    eng_font.selection.none()
    jp_font.selection.none()

    # IBM Plex Sans JP グリフを使用
    eng_font[0x00A2].clear()  # Cent Sign
    eng_font[0x00A3].clear()  # Pound Sign
    eng_font[0x00A5].clear()  # Yen Sign
    eng_font[0x3000].clear()  # 全角スペース
    # U+274C (CROSS MARK) を削除 (OSに含まれる絵文字フォントにフォールバックさせるため)
    eng_font[0x274C].clear()
    # LATIN 系グリフには IBM Plex Mono を使用
    # PlemoCJK: clearing codepoints absent from the alphanumeric side would leave
    # gaps where neither side has the glyph (e.g. IPA at U+0250-0258;
    # affects JIS X 0213 and GBK). Only clear codepoints present in the alphanumeric side.
    eng_unicodes = set()
    for glyph in eng_font.glyphs():
        if glyph.unicode > 0 and glyph.isWorthOutputting():
            eng_unicodes.add(glyph.unicode)
        if glyph.altuni:
            for u in glyph.altuni:
                eng_unicodes.add(u[0])
    for glyph in jp_font.glyphs():
        if glyph.unicode not in eng_unicodes:
            continue
        if 0x00C0 <= glyph.unicode <= 0x00D6:
            glyph.clear()
        elif 0x00D8 <= glyph.unicode <= 0x00F6:
            glyph.clear()
        elif 0x00F8 <= glyph.unicode <= 0x0259:
            glyph.clear()

    # 重複グリフを選択する
    for glyph in jp_font.glyphs("encoding"):
        if glyph.isWorthOutputting() and glyph.unicode > 0:
            try:
                eng_font.selection.select(("more", "unicode"), glyph.unicode)
            except ValueError:
                # Encoding is out of range のときは継続する
                continue
        # altuni が設定されている場合は altuni にも選択を拡張する
        if glyph.altuni:
            for u in glyph.altuni:
                try:
                    eng_font.selection.select(("more", "unicode"), u[0])
                except ValueError:
                    # Encoding is out of range のときは継続する
                    continue

    eng_font.selection.select(("more", "unicode"), 0x0301)

    # 削除箇所に altuni が設定されている場合は削除する前にコピーする
    for glyph in eng_font.selection.byGlyphs:
        jp_font.selection.select(("more", "unicode"), glyph.unicode)
    altuni_glyph_list = []
    for glyph in jp_font.selection.byGlyphs:
        if glyph.altuni:
            altuni_glyph_list.append(glyph.unicode)
            for u in glyph.altuni:
                print(f"Copying glyph U+{glyph.unicode:04X} to U+{u[0]:04X}")
    jp_font = materialize_altuni_glyphs(jp_font, altuni_glyph_list)
    jp_font.selection.none()

    # altuni の整理で各グリフの状態が変わった可能性があるので重複グリフを再選択する
    eng_font.selection.none()
    for glyph in jp_font.glyphs("encoding"):
        try:
            if glyph.isWorthOutputting() and glyph.unicode > 0:
                eng_font.selection.select(("more", "unicode"), glyph.unicode)
        except ValueError:
            # Encoding is out of range のときは継続する
            continue

    # 重複するグリフを削除
    for glyph in eng_font.selection.byGlyphs:
        jp_font.selection.select(("more", "unicode"), glyph.unicode)
    for glyph in jp_font.selection.byGlyphs:
        glyph.clear()

    jp_font.selection.none()
    eng_font.selection.none()

    return jp_font


def materialize_altuni_glyphs(font, entity_glyph_unicode_list):
    """altuni を指定している参照元のコードポイントにグリフをコピーし、
    参照先 (実体) の altuni を削除する。異体字セレクタ分はスキップする。
    """

    for unicode in entity_glyph_unicode_list:
        entity_glyph = font[unicode]
        if not entity_glyph.altuni:
            continue

        # 以下形式のタプルで返ってくる
        # (unicode-value, variation-selector, reserved-field)
        # 第3フィールドは常に0なので無視
        altunis = entity_glyph.altuni

        # 参照先の altuni を削除
        # これをやらないと、グリフのコピー時に altuni が参照されてしまい、
        # 同じコードポイントに貼り付いてしまって意味がない
        entity_glyph.altuni = None

        processed = []
        for altuni in altunis:
            if altuni[0] in processed:
                continue
            if altuni[1] != -1:
                # variation-selector が -1 以外の場合は異体字セレクタなのでスキップ
                continue
            processed.append(altuni[0])
            # altuni 参照元に空グリフを作成
            copy_target_unicode = altuni[0]
            try:
                entity_glyph.glyphname = f"uni{entity_glyph.unicode:04X}"
                copied_glyph_name = f"uni{copy_target_unicode:04X}"
                if copied_glyph_name == entity_glyph.glyphname:
                    copied_glyph_name += "copy"
                copy_target_glyph = font.createChar(
                    copy_target_unicode,
                    copied_glyph_name,
                )
            except Exception:
                copy_target_glyph = font[copy_target_unicode]
            copy_target_glyph.width = entity_glyph.width
            # altuni 参照元へグリフをコピー
            font.selection.select(entity_glyph.glyphname)
            font.copy()
            font.selection.select(copy_target_glyph.glyphname)
            font.paste()

    # alt_uni 処理後、エンコーディングがずれるためか一部のグリフの select() がうまくいかなくなるので開き直す
    font_path = f"{BUILD_FONTS_DIR}/{font.fullname}_{uuid.uuid4()}.ttf"
    font.generate(font_path)
    font.close()
    font = fontforge.open(font_path)
    # 一時ファイルを削除
    os.remove(font_path)

    return font


def delete_not_console_glyphs(eng_font):
    """Clear from the alphanumeric font only the symbols we want full-width from
    the CJK side. Everything else stays half-width from IBM Plex Mono, because
    delete_duplicate_glyphs lets the eng side win on shared codepoints.

    PlemoCJK: the full-width list uses a narrow style. Operators and text-attached
    marks (§ ° ± × ÷ ¶ © ® ™, primes, quotes) stay half-width, and only arrows and
    CJK-style marks go full-width. This makes about 70 symbols half-width that
    PlemolJP used to force full-width.

    Notes:
    - Cyrillic is left out on purpose, so it stays half-width from IBM Plex Mono
      (JP has only about half the block; see adjust_letter_script_width).
    - Quotes U+2018/2019/201C/201D are half-width for every region, so Chinese
      does not need a separate full-width form here.
    - ‰ № ℡ are CJK-style marks, so they stay full-width.
    - Mathematical Operators (U+2200-22FF) are not listed: the ones IBM Plex Mono
      covers (√ ∞ ∑ ∫ ≤ ≥ ≠ …) come half-width from it; the rest (⊕ ⊗ ∈ ∮ ≪ …)
      stay full-width from the JP side, like upstream -- squeezing them to half
      would thin their strokes and distort circles.
    """
    full_width_syms = [
        # em/CJK dashes and leaders
        0x2014, 0x2015, 0x2025, 0x2026,
        # CJK-flavoured marks
        0x2030, 0x203B, 0x203E, 0x2116, 0x2121,
        # arrows
        0x2190, 0x2191, 0x2192, 0x2193,
        0x2196, 0x2197, 0x2198, 0x2199,
        0x21C4, 0x21C5, 0x21C6, 0x21D2, 0x21D4,
        0x21E6, 0x21E7, 0x21E8, 0x21E9, 0x21F5,
    ]
    eng_font.selection.none()
    for cp in full_width_syms:
        try:
            eng_font.selection.select(("more", "unicode"), cp)
        except ValueError:
            # eng font lacks this codepoint; the JP glyph already survives.
            continue

    for glyph in eng_font.selection.byGlyphs:
        glyph.clear()

    eng_font.selection.none()


def remove_lookups(font, remove_gsub=True, remove_gpos=True):
    """GSUB, GPOSテーブルを削除する"""
    if remove_gsub:
        for lookup in font.gsub_lookups:
            font.removeLookup(lookup)
    if remove_gpos:
        for lookup in font.gpos_lookups:
            font.removeLookup(lookup)


def transform_italic_glyphs(font):
    """日本語フォントの斜体を生成する"""
    # 傾きを設定する
    font.italicangle = -ITALIC_ANGLE
    # 全グリフを斜体に変換
    for glyph in font.glyphs():
        orig_width = glyph.width
        glyph.transform(psMat.skew(ITALIC_ANGLE * math.pi / 180))
        glyph.transform(psMat.translate(-40, 0))
        glyph.width = orig_width


def adjust_letter_script_width(jp_font):
    """Make alphabetic scripts that fall to the CJK side half-width (1 cell) in
    every variant, so a word reads uniformly instead of being split into
    half- and full-width letters.

    Covers Greek + Greek Extended, Cyrillic and IPA. Keyed on the Unicode block
    rather than East Asian Width on purpose: within these scripts EAW is mixed
    (accented Greek ί/ά and the extended Cyrillic letters are Neutral while the
    base letters are Ambiguous), so keying on EAW=A would split a script.

    Only JP-sourced glyphs are affected here (Greek/IPA come entirely from JP).
    Cyrillic is served half-width from IBM Plex Mono instead -- see
    delete_not_console_glyphs, which no longer removes it from the eng side --
    because JP does not cover ~100 of the extended Cyrillic letters; this loop
    is a no-op for it but keeps the range documented and catches any JP-only
    Cyrillic. Runs before set_width_600_or_1000, emitting 500 which becomes the
    600 half-width intermediate.
    """
    half_cell = 500      # pipeline half-width intermediate (-> 528 / 600 final)
    # Max ink allowed in the cell. Kept below half_cell so a side bearing always
    # survives to the final cell (~24u in the 528 default half-cell, ~60u in the
    # 600 console one) -- so a trimmed glyph never ends flush against the edge
    # (post-trim collisions). Also keeps mid-width letters near IBM Plex Mono's
    # own ~0.93 horizontal scale rather than thinning them further.
    ink_budget = 480
    for glyph in jp_font.glyphs():
        cp = glyph.unicode
        # width<=0 skips combining marks (kept zero-width, never boxed)
        if cp < 0 or glyph.width <= 0:
            continue
        if not (
            0x0250 <= cp <= 0x02AF          # IPA Extensions
            or 0x0370 <= cp <= 0x03FF       # Greek and Coptic
            or 0x0400 <= cp <= 0x04FF       # Cyrillic
            or 0x1F00 <= cp <= 0x1FFF       # Greek Extended
        ):
            continue
        # Fit by real INK (bounding box), not the advance: scale down ONLY when
        # the ink itself overflows the budget, so glyphs whose ink already fits
        # are re-centered (bearings trimmed) rather than thinned. boundingBox
        # captures any designed overhang / negative side-bearing, so a glyph that
        # legitimately sits flush is measured and repositioned correctly.
        bb = glyph.boundingBox()
        ink = bb[2] - bb[0]
        if ink > ink_budget:
            glyph.transform(psMat.scale(ink_budget / ink, 1))
            bb = glyph.boundingBox()
        # Center the ink -> symmetric, always-positive bearings.
        glyph.transform(psMat.translate((half_cell - (bb[0] + bb[2])) / 2, 0))
        glyph.width = half_cell


def set_width_600_or_1000(jp_font):
    """半角幅か全角幅になるように変換する

    PlemoCJK: Hangul syllables in IBM Plex Sans KR have width 892, so they fall
    into the "500 < width < 1000 -> center to 1000" branch and become full-width.
    All 4 regions go through this same path, so the output Hangul glyphs are
    byte-identical and TTC glyf sharing works.
    Half-width Hangul Jamo (U+FFA1-FFDC) are kept at half-width.
    """
    for glyph in jp_font.glyphs():
        if is_half_width_hangul(glyph.unicode):
            # 半角のまま (後続の 500 -> 600 の正規化だけは通す)
            if 0 < glyph.width < 500:
                glyph.transform(psMat.translate((500 - glyph.width) / 2, 0))
                glyph.width = 500
            if glyph.width == 500:
                glyph.transform(psMat.translate((600 - glyph.width) / 2, 0))
                glyph.width = 600
            continue
        if 0 < glyph.width < 500:
            # グリフ位置を調整してから幅を設定
            glyph.transform(psMat.translate((500 - glyph.width) / 2, 0))
            glyph.width = 500
        elif (
            500 < glyph.width < 1000 or 0xC0 <= glyph.unicode <= 0x192
        ):  # 特定のアルファベット関連文字 0xC0 - 0x192 は全角幅にする
            # グリフ位置を調整してから幅を設定
            glyph.transform(psMat.translate((1000 - glyph.width) / 2, 0))
            glyph.width = 1000
        elif glyph.width > 1000:
            # Advance exceeds a full cell (wide Cyrillic Ж Ш Щ Ю, ‰, ≪ ≫).
            # Snap to full width; compress only when the ink itself overflows
            # the cell (e.g. ‰), otherwise keep the shape and just re-center
            # the ink -- most of these are merely padded, not over-wide.
            bb = glyph.boundingBox()
            ink = bb[2] - bb[0]
            if ink > 1000:
                glyph.transform(psMat.scale(1000 / ink, 1))
                bb = glyph.boundingBox()
            glyph.transform(psMat.translate((1000 - (bb[0] + bb[2])) / 2, 0))
            glyph.width = 1000

        # 500幅の場合は一旦 600 幅にする
        if glyph.width == 500:
            glyph.transform(psMat.translate((600 - glyph.width) / 2, 0))
            glyph.width = 600

        # なぜか標準の幅ではないグリフの個別調整
        if glyph.unicode == 0x51F0:
            glyph.transform(psMat.translate((1000 - glyph.width) / 2, 0))
            glyph.width = 1000
        if glyph.glyphname == "perthousand.full":
            glyph.width = 1000


def adjust_width_35_eng(eng_font):
    """英語フォントを半角3:全角5幅になるように変換する"""
    original_half_width = eng_font[0x0030].width
    after_width = int(FULL_WIDTH_35 * 3 / 5)
    x_scale = after_width / original_half_width
    for glyph in eng_font.glyphs():
        if 0 < glyph.width < after_width:
            # after_width より幅が狭い場合は位置合わせしてから幅を設定
            glyph.transform(psMat.translate((after_width - glyph.width) / 2, 0))
            glyph.width = after_width
        elif after_width < glyph.width <= original_half_width:
            # after_width より幅が広い、かつ元の半角幅より狭い場合は縮小してから幅を設定
            glyph.transform(psMat.scale(x_scale, 1))
            glyph.width = after_width
        elif original_half_width < glyph.width:
            # after_width より幅が広い (おそらく全てリガチャ) の場合は倍数にする
            multiply_number = round(glyph.width / original_half_width)
            glyph.transform(psMat.scale(x_scale, 1))
            glyph.width = after_width * multiply_number


def adjust_width_35_jp(jp_font):
    """日本語フォントを半角3:全角5幅になるように変換する"""
    after_width = int(FULL_WIDTH_35 * 3 / 5)
    jp_half_width = jp_font[0x3000].width / 2
    jp_full_width = jp_font[0x3000].width
    for glyph in jp_font.glyphs():
        if glyph.width == jp_half_width:
            glyph.transform(psMat.translate((after_width - glyph.width) / 2, 0))
            glyph.width = after_width
        elif glyph.width == jp_full_width:
            glyph.transform(psMat.translate((FULL_WIDTH_35 - glyph.width) / 2, 0))
            glyph.width = FULL_WIDTH_35


def adjust_width_36_jp(jp_font):
    """Expand full-width CJK glyphs from 1000 to 1200 (half 600 : full 1200)"""
    for glyph in jp_font.glyphs():
        if glyph.width == 1000:
            glyph.transform(psMat.translate((FULL_WIDTH_36 - glyph.width) / 2, 0))
            glyph.width = FULL_WIDTH_36


def transform_half_width(jp_font, eng_font):
    """1:2幅になるように変換する"""
    before_width_eng = eng_font[0x0030].width
    after_width_eng = HALF_WIDTH_12
    # 単純な 縮小後幅 / 元の幅 だと狭くなりすぎるので、分子は大きめにする (546 > 528)。
    x_scale = 546 / before_width_eng
    for glyph in eng_font.glyphs():
        if glyph.width > 0:
            # リガチャ考慮
            after_width_eng_multiply = after_width_eng * round(
                glyph.width / before_width_eng
            )
            # 縮小
            glyph.transform(psMat.scale(x_scale, 0.97))
            # 幅を設定
            glyph.transform(
                psMat.translate((after_width_eng_multiply - glyph.width) / 2, 0)
            )
            glyph.width = after_width_eng_multiply

    for glyph in jp_font.glyphs():
        if glyph.width == 600:
            # 英数字グリフと同じ幅にする
            glyph.transform(psMat.translate((after_width_eng - glyph.width) / 2, 0))
            glyph.width = after_width_eng
        elif glyph.width == 1000:
            # 全角は after_width_eng の倍の幅にする
            glyph.transform(psMat.translate((after_width_eng * 2 - glyph.width) / 2, 0))
            glyph.width = after_width_eng * 2


def make_box_drawing_full_width(eng_font, jp_font):
    """罫線を全角にする"""
    # 英語フォント側は完全に削除
    eng_font.selection.select(("unicode", "ranges"), 0x2500, 0x257F)
    for glyph in eng_font.selection.byGlyphs:
        glyph.clear()
    eng_font.selection.none()
    # 日本語フォント側は削除してから全角用グリフをマージする
    jp_font.selection.select(("unicode", "ranges"), 0x2500, 0x257F)
    for glyph in jp_font.selection.byGlyphs:
        glyph.clear()
    jp_font.selection.none()
    jp_font.mergeFonts(fontforge.open(f"{SOURCE_FONTS_DIR}/FullWidthBoxDrawings.sfd"))
    # 幅設定と位置調整
    width_to = jp_font[0x3042].width
    jp_font.selection.select(("unicode", "ranges"), 0x2500, 0x257F)
    for glyph in jp_font.selection.byGlyphs:
        # 幅が調整前より広がる場合は拡大する
        width_from = glyph.width
        if width_from < width_to:
            glyph.transform(psMat.scale(width_to / width_from, 1))
        width_from = glyph.width
        glyph.transform(psMat.translate((width_to - width_from) / 2, 0))
        glyph.width = width_to
    jp_font.selection.none()


def fit_block_line_height(eng_font):
    """Fit the solid Block Elements (U+2580-259F; ░▒▓ shades are done in
    apply_shade_blocks) to exactly the typo/hhea line box so they fill one line
    and tile down with no gap. Mono draws them ~1300 tall (its own line);
    transform_half_width leaves ~1262. One linear y-map keyed on U+2588 keeps the
    fractions (█ full, ▄/▀ halves, eighths). Both variants."""
    fb = eng_font[0x2588].boundingBox()
    ch = fb[3] - fb[1]
    if ch <= 0:
        return
    ty0, ty1 = -TYPO_DESCENT, TYPO_ASCENT
    sy = (ty1 - ty0) / ch
    dy = ty0 - fb[1] * sy
    eng_font.selection.select(("unicode", "ranges"), 0x2580, 0x259F)
    for glyph in list(eng_font.selection.byGlyphs):
        if glyph.width <= 0 or 0x2591 <= glyph.unicode <= 0x2593:
            continue
        glyph.transform(psMat.scale(1, sy))
        glyph.transform(psMat.translate(0, dy))
    eng_font.selection.none()


def make_block_elements_full_width(eng_font, full_width):
    """Widen the solid Block Elements (U+2580-259F) from half-cell to full-cell.
    They are edge-anchored (█ fills, ▌ left, ▐ right, eighths, quadrants), so
    each is scaled horizontally FROM THE ORIGIN -- no re-centering, or left/right
    anchoring would break. The scale comes from U+2588, whose ink already spans
    one cell, so every block lands exactly on the full cell with no overflow or
    gap (scaling by the advance would leave ink ~3% over, as transform_half_width
    widens ink past the advance). Vertical is fit_block_line_height's job, shades
    ░▒▓ are apply_shade_blocks's, so both are skipped. Non-console only."""
    cell = eng_font[0x2588].boundingBox()
    cell = cell[2] - cell[0]  # current one-cell ink width
    if cell <= 0:
        return
    sx = full_width / cell
    eng_font.selection.select(("unicode", "ranges"), 0x2580, 0x259F)
    for glyph in list(eng_font.selection.byGlyphs):
        if glyph.width <= 0 or 0x2591 <= glyph.unicode <= 0x2593:
            continue
        glyph.transform(psMat.scale(sx, 1))
        glyph.width = full_width
    eng_font.selection.none()


def apply_shade_blocks(eng_font, style, target_width, doubled):
    """Replace the shade blocks ░▒▓ (U+2591-2593) with Hack's square
    checkerboard (Mono's are round dots that stretch to ovals in a wider cell;
    Hack is already a source). Each is stretched to fill U+2588's width and the
    typo/hhea line box, so shades match the solids and tile seamlessly -- the
    dots go non-square, but filling the cell matters more for a texture.
    doubled=True (full cell) first tiles two copies side by side so the full
    cell keeps the half cell's pattern density."""
    tb = eng_font[0x2588].boundingBox()  # solid block = the horizontal reference
    tx0, tx1 = tb[0], tb[2]
    ty0, ty1 = -TYPO_DESCENT, TYPO_ASCENT  # exactly one line high
    tw, th = tx1 - tx0, ty1 - ty0
    if tw <= 0 or th <= 0:
        return
    hack_style = "Bold" if "Bold" in style else "Regular"
    hack = fontforge.open(f"{SOURCE_FONTS_DIR}/" + HACK_FONT.replace("{style}", hack_style))
    hack.em = EM_ASCENT + EM_DESCENT
    for cp in (0x2591, 0x2592, 0x2593):
        try:
            g = hack[cp]
        except TypeError:
            continue
        adv = g.width
        if adv <= 0:
            continue
        if doubled:
            fg = g.foreground
            shifted = fg.dup()
            shifted.transform(psMat.translate(adv, 0))
            g.foreground = fg + shifted
        b = g.boundingBox()
        bw, bh = b[2] - b[0], b[3] - b[1]
        if bw <= 0 or bh <= 0:
            continue
        g.transform(psMat.scale(tw / bw, th / bh))
        b = g.boundingBox()
        g.transform(psMat.translate(tx0 - b[0], ty0 - b[1]))
        g.width = target_width
        hack.selection.select(("unicode", None), cp)
        hack.copy()
        eng_font.selection.select(("unicode", None), cp)
        eng_font.paste()
        eng_font[cp].width = target_width
    hack.close()
    eng_font.selection.none()


def visualize_zenkaku_space(jp_font):
    """全角スペースを可視化する"""
    # 全角スペースを差し替え
    glyph = jp_font[0x3000]
    width_to = glyph.width
    glyph.clear()
    jp_font.mergeFonts(fontforge.open(f"{SOURCE_FONTS_DIR}/{IDEOGRAPHIC_SPACE}"))
    # 幅を設定し位置調整
    jp_font.selection.select("U+3000")
    for glyph in jp_font.selection.byGlyphs:
        width_from = glyph.width
        glyph.transform(psMat.translate((width_to - width_from) / 2, 0))
        glyph.width = width_to
    jp_font.selection.none()


def merge_hack(jp_font, eng_font, style):
    """Hack フォントをマージする"""
    if "Bold" in style:
        hack_font = fontforge.open(
            f"{SOURCE_FONTS_DIR}/" + HACK_FONT.replace("{style}", "Bold")
        )
    else:
        hack_font = fontforge.open(
            f"{SOURCE_FONTS_DIR}/" + HACK_FONT.replace("{style}", "Regular")
        )
    hack_font.em = EM_ASCENT + EM_DESCENT
    # 既に英語フォント側に存在する場合はhackグリフは削除する
    for glyph in eng_font.glyphs():
        if glyph.unicode != -1:
            try:
                for g in hack_font.selection.select(
                    ("unicode", None), glyph.unicode
                ).byGlyphs:
                    g.clear()
            except Exception:
                pass
    if options.get("console"):
        # Console版では、日本語フォントよりhackフォントのグリフを優先する
        for glyph in hack_font.glyphs():
            if glyph.unicode != -1:
                try:
                    for g in jp_font.selection.select(
                        ("unicode", None), glyph.unicode
                    ).byGlyphs:
                        g.clear()
                except Exception:
                    pass
    else:
        # 既に日本語フォント側に存在する場合はhackグリフは削除する
        for glyph in jp_font.glyphs():
            if glyph.unicode != -1:
                try:
                    for g in hack_font.selection.select(
                        ("unicode", None), glyph.unicode
                    ).byGlyphs:
                        g.clear()
                except Exception:
                    pass
    # EM 1000 にしたときの幅に合わせて調整
    half_width = int(FULL_WIDTH_35 * 3 / 5)
    for glyph in hack_font.glyphs():
        if glyph.width > 0:
            glyph.transform(psMat.translate((half_width - glyph.width) / 2, 0))
            glyph.width = half_width
    # Hack フォントをオブジェクトとして扱いたくないので、一旦ファイル保存して直接マージする
    font_path = f"{BUILD_FONTS_DIR}/tmp_hack_{uuid.uuid4()}.ttf"
    hack_font.generate(font_path)
    hack_font.close()

    eng_font.mergeFonts(font_path)
    os.remove(font_path)


def eaaw_width_to_half(jp_font):
    """East Asian Ambiguous Width 文字の半角化"""
    # ref: https://www.unicode.org/Public/15.1.0/ucd/EastAsianWidth.txt

    eaaw_unicode_list = (
        0x203B,  # REFERENCE MARK
        0x2103,
        0x2109,
        0x2121,
        0x212B,
        *range(0x2160, 0x216B + 1),
        *range(0x2170, 0x217B + 1),
        0x221F,
        0x222E,
        *range(0x226A, 0x226B + 1),
        0x22A5,
        0x22BF,
        0x2312,
        *range(0x2460, 0x2490 + 1),
        *range(0x249C, 0x24B5 + 1),
        *range(0x2605, 0x2606 + 1),
        0x260E,
        0x261C,
        0x261E,
        0x2640,
        0x2642,
        *range(0x2660, 0x2665 + 1),
        0x2667,
        0x266A,
        0x266D,
        0x266F,
        0x1F100,
    )
    half_width = 500
    for glyph in jp_font.glyphs():
        if glyph.unicode in eaaw_unicode_list and glyph.width > half_width:
            glyph.transform(psMat.scale(0.67, 0.9))
            glyph.transform(psMat.translate((half_width - glyph.width) / 2, 0))
            glyph.width = half_width


def add_console_glyphs(eng_font):
    eng_width = eng_font[0x0030].width

    # HEAVY CHECK MARK (U+2714) を追加
    # この記号は Docker コマンドなどで使用されている
    eng_font.selection.select(("unicode", None), 0x2713)
    eng_font.copy()
    eng_font.selection.select(("unicode", None), 0x2714)
    eng_font.paste()
    for glyph in eng_font.selection.byGlyphs:
        glyph.stroke("circular", 35, removeinternal=True)
        glyph.width = eng_width

    eng_font.selection.none()


def scale_glyph_from_center(glyph, scale_x, scale_y):
    """グリフの中心位置を基点としたスケール調整"""
    original_width = glyph.width
    # スケール前の中心位置を求める
    before_bb = glyph.boundingBox()
    before_center_x = (before_bb[0] + before_bb[2]) / 2
    before_center_y = (before_bb[1] + before_bb[3]) / 2
    # スケール変換
    glyph.transform(psMat.scale(scale_x, scale_y))
    # スケール後の中心位置を求める
    after_bb = glyph.boundingBox()
    after_center_x = (after_bb[0] + after_bb[2]) / 2
    after_center_y = (after_bb[1] + after_bb[3]) / 2
    # 拡大で増えた分を考慮して中心位置を調整
    glyph.transform(
        psMat.translate(
            before_center_x - after_center_x,
            before_center_y - after_center_y,
        )
    )
    glyph.width = original_width


def down_scale_redundant_size_glyph(eng_font):
    """規定の幅からはみ出したグリフサイズを縮小する"""

    for glyph in eng_font.glyphs():
        xmin = glyph.boundingBox()[0]
        xmax = glyph.boundingBox()[2]

        if (
            glyph.width > 0
            and -15
            < xmin
            < 0  # 特定幅より左にはみ出している場合、意図的にはみ出しているものと見なして無視
            and abs(xmin) - 10
            < xmax - glyph.width
            < abs(xmin) + 10  # はみ出し幅が左側と右側で極端に異なる場合は無視
            and not (
                0x0020 <= glyph.unicode <= 0x02AF
            )  # latin 系のグリフ 0x0020 - 0x0192 は無視
            and not (
                0xE0B0 <= glyph.unicode <= 0xE0D4
            )  # Powerline系のグリフ 0xE0B0 - 0xE0D4 は無視
            and not (
                0x2500 <= glyph.unicode <= 0x257F
            )  # 罫線系のグリフ 0x2500 - 0x257F は無視
            and not (
                0x2591 <= glyph.unicode <= 0x2593
            )  # SHADE グリフ 0x2591 - 0x2593 は無視
        ):
            scale_glyph_from_center(glyph, 1 + (xmin / glyph.width) * 2, 1)


def add_nerd_font_glyphs(jp_font, eng_font):
    """Nerd Fontのグリフを追加する"""
    global nerd_font
    # Nerd Fontのグリフを追加する
    if nerd_font is None:
        nerd_font = fontforge.open(
            f"{SOURCE_FONTS_DIR}/nerd-fonts/SymbolsNerdFont-Regular.ttf"
        )
        nerd_font.em = EM_ASCENT + EM_DESCENT
        glyph_names = set()
        for nerd_glyph in nerd_font.glyphs():
            # Nerd Fontsのグリフ名をユニークにするため接尾辞を付ける
            nerd_glyph.glyphname = f"{nerd_glyph.glyphname}-nf"
            # postテーブルでのグリフ名重複対策
            # fonttools merge で合成した後、MacOSで `'post'テーブルの使用性` エラーが発生することへの対処
            if nerd_glyph.glyphname in glyph_names:
                nerd_glyph.glyphname = f"{nerd_glyph.glyphname}-{nerd_glyph.encoding}"
            glyph_names.add(nerd_glyph.glyphname)
            # 幅を調整する
            half_width = eng_font[0x0030].width
            # Powerline Symbols の調整
            if 0xE0B0 <= nerd_glyph.unicode <= 0xE0D7:
                # 位置と幅合わせ
                if nerd_glyph.width < half_width:
                    nerd_glyph.transform(
                        psMat.translate((half_width - nerd_glyph.width) / 2, 0)
                    )
                elif nerd_glyph.width > half_width:
                    nerd_glyph.transform(psMat.scale(half_width / nerd_glyph.width, 1))
                # グリフの高さ・位置を調整する
                nerd_glyph.transform(psMat.scale(1, 1.14))
                nerd_glyph.transform(psMat.translate(0, 21))
            elif nerd_glyph.width < (EM_ASCENT + EM_DESCENT) * 0.6:
                # 幅が狭いグリフは中央寄せとみなして調整する
                nerd_glyph.transform(
                    psMat.translate((half_width - nerd_glyph.width) / 2, 0)
                )
            # 幅を設定
            nerd_glyph.width = half_width
    # 日本語フォントにマージするため、既に存在する場合は削除する
    for nerd_glyph in nerd_font.glyphs():
        if nerd_glyph.unicode != -1:
            # 既に存在する場合は削除する
            try:
                for glyph in jp_font.selection.select(
                    ("unicode", None), nerd_glyph.unicode
                ).byGlyphs:
                    glyph.clear()
            except Exception:
                pass
            try:
                for glyph in eng_font.selection.select(
                    ("unicode", None), nerd_glyph.unicode
                ).byGlyphs:
                    glyph.clear()
            except Exception:
                pass

    jp_font.mergeFonts(nerd_font)

    jp_font.selection.none()
    eng_font.selection.none()


def delete_glyphs_with_duplicate_glyph_names(font):
    """重複するグリフ名を持つグリフをリネームする"""
    glyph_name_set = set()
    for glyph in font.glyphs():
        if glyph.glyphname in glyph_name_set:
            glyph.glyphname = f"{glyph.glyphname}_{glyph.encoding}"
        else:
            glyph_name_set.add(glyph.glyphname)


def edit_meta_data(font, weight: str, variant: str, cap_height: int, x_height: int):
    """フォント内のメタデータを編集する"""
    font.ascent = EM_ASCENT
    font.descent = EM_DESCENT

    font.os2_winascent = WIN_ASCENT
    font.os2_windescent = WIN_DESCENT

    font.os2_typoascent = TYPO_ASCENT
    font.os2_typodescent = -TYPO_DESCENT
    font.os2_typolinegap = 0

    font.hhea_ascent = TYPO_ASCENT
    font.hhea_descent = -TYPO_DESCENT
    font.hhea_linegap = 0

    font.os2_xheight = x_height
    font.os2_capheight = cap_height

    # VSCode のターミナル上のボトム位置の表示で g, j などが見切れる問題への対処
    # 水平ベーステーブルを削除
    font.horizontalBaseline = None

    if "Regular" == weight or "Italic" == weight:
        font.os2_weight = 400
    elif "Thin" in weight:
        font.os2_weight = 100
    elif "ExtraLight" in weight:
        font.os2_weight = 200
    elif "Light" in weight:
        font.os2_weight = 300
    elif "Text" in weight:
        font.os2_weight = 450
    elif "Medium" in weight:
        font.os2_weight = 500
    elif "SemiBold" in weight:
        font.os2_weight = 600
    elif "Bold" in weight:
        font.os2_weight = 700

    font.os2_vendor = VENDER_NAME

    font.sfnt_names = (
        (
            "English (US)",
            "License",
            """This Font Software is licensed under the SIL Open Font License,
Version 1.1. This license is available with a FAQ
at: http://scripts.sil.org/OFL""",
        ),
        ("English (US)", "License URL", "http://scripts.sil.org/OFL"),
        ("English (US)", "Version", VERSION),
        ("English (US)", "Copyright", COPYRIGHT),
    )

    # フォント名を設定する
    if (
        "Regular" == weight
        or "Italic" == weight
        or "Bold" == weight
        or "BoldItalic" == weight
    ):
        font_family = FONT_NAME
        if variant != "":
            font_family += f" {variant}".replace(" 35", "35").replace(" 36", "36")
        font_weight = weight
        if weight == "BoldItalic":
            font_weight = font_weight.replace("Italic", " Italic")
        font.familyname = font_family
        # フォントサブファミリー名
        font.appendSFNTName(0x409, 2, font_weight)
        font.fontname = f"{font_family}-{font_weight}".replace(" ", "")
        font.fullname = f"{font_family} {font_weight}"
        font.weight = font_weight.split(" ")[0]
    else:
        font_family = FONT_NAME
        if variant != "":
            font_family += f" {variant}".replace(" 35", "35").replace(" 36", "36")
        font_weight = weight
        if "Italic" in weight:
            font_weight = font_weight.replace("Italic", " Italic")
        font.familyname = f"{font_family} " + font_weight.split(" ")[0]
        # フォントサブファミリー名
        if "Italic" in weight:
            font.appendSFNTName(0x409, 2, "Italic")
        else:
            font.appendSFNTName(0x409, 2, "Regular")
        font.fontname = f"{font_family}-{font_weight}".replace(" ", "")
        font.fullname = f"{font_family} {font_weight}"
        font.weight = font_weight.split(" ")[0]
        # 優先フォントファミリー名
        font.appendSFNTName(0x409, 16, font_family)
        # 優先フォントスタイル
        font.appendSFNTName(0x409, 17, font_weight)


if __name__ == "__main__":
    main()
