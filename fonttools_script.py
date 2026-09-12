#!/bin/env python3

import configparser
import glob
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from fontTools import merge, ttLib, ttx
from ttfautohint import options, ttfautohint

import plemocjk_config
import plemocjk_metadata

# iniファイルを読み込む
settings = configparser.ConfigParser()
settings.read("build.ini", encoding="utf-8")

FONT_NAME = settings.get("DEFAULT", "FONT_NAME")
FONTFORGE_PREFIX = settings.get("DEFAULT", "FONTFORGE_PREFIX")
FONTTOOLS_PREFIX = settings.get("DEFAULT", "FONTTOOLS_PREFIX")
BUILD_FONTS_DIR = settings.get("DEFAULT", "BUILD_FONTS_DIR")
HALF_WIDTH_12 = int(settings.get("DEFAULT", "HALF_WIDTH_12"))
FULL_WIDTH_35 = int(settings.get("DEFAULT", "FULL_WIDTH_35"))
FULL_WIDTH_36 = int(settings.get("DEFAULT", "FULL_WIDTH_36"))
WIDTH_35_STR = settings.get("DEFAULT", "WIDTH_35_STR")
WIDTH_36_STR = settings.get("DEFAULT", "WIDTH_36_STR")
CONSOLE_STR = settings.get("DEFAULT", "CONSOLE_STR")


def usage():
    print(
        f"Usage:\n"
        f"  {sys.argv[0]} --eng-hint <variant>       # 英数字側に ttfautohint を掛ける\n"
        f"  {sys.argv[0]} <variant> [<region>]       # 結合してテーブルを整える"
    )


def main():
    # 第一引数を取得
    # 特定のバリエーションのみを処理するための指定
    if len(sys.argv) > 1 and sys.argv[1] == "--eng-hint":
        hint_eng_fonts(sys.argv[2] if len(sys.argv) > 2 else "")
        return

    specific_variant = sys.argv[1] if len(sys.argv) > 1 else None
    region = sys.argv[2] if len(sys.argv) > 2 else None

    edit_fonts(specific_variant, region)


def hint_eng_fonts(eng_variant: str):
    """Apply ttfautohint to alphanumeric-side fonts (region-independent)"""
    file_pattern = f"{FONTFORGE_PREFIX}{FONT_NAME}{eng_variant}*-eng.ttf"
    filenames = sorted(glob.glob(f"{BUILD_FONTS_DIR}/{file_pattern}"))
    if len(filenames) == 0:
        print(f"Error: {file_pattern} not found")
        raise SystemExit(1)
    for filename in filenames:
        path = Path(filename)
        if path.stem.endswith("-eng-hinted"):
            continue
        style = path.stem.split("-")[1]
        variant = path.stem.split("-")[0].replace(f"{FONTFORGE_PREFIX}{FONT_NAME}", "")
        print(f"hint {filename}")
        add_hinting(filename, filename.replace(".ttf", "-hinted.ttf"), variant, style)


def edit_fonts(specific_variant: str, region: str = None):
    """フォントを編集する"""

    if specific_variant is None:
        specific_variant = ""

    # ファイルをパターンで指定
    file_pattern = f"{FONTFORGE_PREFIX}{FONT_NAME}{specific_variant}*-jp.ttf"
    filenames = glob.glob(f"{BUILD_FONTS_DIR}/{file_pattern}")
    # ファイルが見つからない場合はエラー
    if len(filenames) == 0:
        print(f"Error: {file_pattern} not found")
        return
    paths = [Path(f) for f in filenames]
    for path in paths:
        print(f"edit {str(path)}")
        style = path.stem.split("-")[1]
        variant = path.stem.split("-")[0].replace(f"{FONTFORGE_PREFIX}{FONT_NAME}", "")
        # The alphanumeric-side filename has no region, so strip the region from the modifier
        eng_variant = variant.replace(region, "", 1) if region else variant
        merge_fonts(style, variant, eng_variant)
        fix_font_tables(style, variant)
        if region:
            htag = plemocjk_config.hyphenate_tag(variant)
            plemocjk_metadata.apply(
                f"{BUILD_FONTS_DIR}/{FONT_NAME.replace(' ', '')}-{htag}-{style}.ttf",
                region=region,
                variant_tag=variant,
                style=style,
            )

    # Delete temporary files (keep alphanumeric-side files; other regions still need them)
    # スタイル部分以降はワイルドカードで指定
    for filename in glob.glob(
        f"{BUILD_FONTS_DIR}/{FONTTOOLS_PREFIX}{FONT_NAME}{specific_variant}*"
    ):
        os.remove(filename)
    for filename in glob.glob(
        f"{BUILD_FONTS_DIR}/{FONTFORGE_PREFIX}{FONT_NAME}{specific_variant}*"
    ):
        os.remove(filename)


def add_hinting(input_font_path, output_font_path, variant, style):
    """フォントにヒンティングを付ける"""
    if "Italic" not in style:
        width_variant = "35" if plemocjk_config.width_mode_for_tag(variant) != "12" else "normal"
        ctrl_file = [
            "-m",
            f"hinting_post_process/{width_variant}-{style}-ctrl.txt",
        ]
    else:
        ctrl_file = []

    args = ctrl_file + [
        "-l",
        "6",
        "-r",
        "45",
        "-D",
        "latn",
        "-f",
        "none",
        "-S",
        "-W",
        "-X",
        "13-",
        "-I",
        input_font_path,
        output_font_path,
    ]
    options_ = options.parse_args(args)
    print("exec hinting", options_)
    ttfautohint(**options_)


def merge_fonts(style, variant, eng_variant=None):
    """フォントを結合する"""
    # PlemoCJK: the alphanumeric side is region-independent, so look it up without the region modifier
    if eng_variant is None:
        eng_variant = variant
    eng_font_path = f"{BUILD_FONTS_DIR}/{FONTFORGE_PREFIX}{FONT_NAME}{eng_variant}-{style}-eng-hinted.ttf"
    jp_font_path = (
        f"{BUILD_FONTS_DIR}/{FONTFORGE_PREFIX}{FONT_NAME}{variant}-{style}-jp.ttf"
    )
    # vhea, vmtxテーブルを削除
    jp_font_object = ttLib.TTFont(jp_font_path)
    if "vhea" in jp_font_object:
        del jp_font_object["vhea"]
    if "vmtx" in jp_font_object:
        del jp_font_object["vmtx"]
    jp_font_object.save(jp_font_path)
    # フォントを結合
    merger = merge.Merger()
    merged_font = merger.merge([eng_font_path, jp_font_path])
    merged_font.save(
        f"{BUILD_FONTS_DIR}/{FONTTOOLS_PREFIX}{FONT_NAME}{variant}-{style}_merged.ttf"
    )


def fix_font_tables(style, variant):
    """フォントテーブルを編集する"""

    input_font_name = f"{FONTTOOLS_PREFIX}{FONT_NAME}{variant}-{style}_merged.ttf"
    output_name_base = f"{FONTTOOLS_PREFIX}{FONT_NAME}{variant}-{style}"
    htag = plemocjk_config.hyphenate_tag(variant)
    completed_name_base = f"{FONT_NAME.replace(' ', '')}-{htag}-{style}"

    # OS/2, post テーブルのみのttxファイルを出力
    xml = dump_ttx(input_font_name, output_name_base)
    # OS/2 テーブルを編集
    wmode = plemocjk_config.width_mode_for_tag(variant)
    fix_os2_table(xml, style, flag_35=wmode == "35", flag_36=wmode == "36")
    # post テーブルを編集
    fix_post_table(xml, flag_wide=wmode == "35")
    # name テーブルを編集
    fix_name_table(xml)

    # ttxファイルを上書き保存
    xml.write(
        f"{BUILD_FONTS_DIR}/{output_name_base}.ttx",
        encoding="utf-8",
        xml_declaration=True,
    )

    # ttxファイルをttfファイルに適用
    ttx.main(
        [
            "-o",
            f"{BUILD_FONTS_DIR}/{output_name_base}_os2_post.ttf",
            "-m",
            f"{BUILD_FONTS_DIR}/{input_font_name}",
            f"{BUILD_FONTS_DIR}/{output_name_base}.ttx",
        ]
    )

    # ファイル名を変更
    os.rename(
        f"{BUILD_FONTS_DIR}/{output_name_base}_os2_post.ttf",
        f"{BUILD_FONTS_DIR}/{completed_name_base}.ttf",
    )


def dump_ttx(input_name_base, output_name_base) -> ET:
    """OS/2, post テーブルのみのttxファイルを出力"""
    ttx.main(
        [
            "-t",
            "OS/2",
            "-t",
            "post",
            "-t",
            "name",
            "-f",
            "-o",
            f"{BUILD_FONTS_DIR}/{output_name_base}.ttx",
            f"{BUILD_FONTS_DIR}/{input_name_base}",
        ]
    )

    return ET.parse(f"{BUILD_FONTS_DIR}/{output_name_base}.ttx")


def fix_os2_table(xml: ET, style: str, flag_35: bool = False, flag_36: bool = False):
    """OS/2 テーブルを編集する"""
    # xAvgCharWidthを編集
    # タグ形式: <xAvgCharWidth value="1000"/>
    if flag_36:
        x_avg_char_width = FULL_WIDTH_36
    elif flag_35:
        x_avg_char_width = FULL_WIDTH_35
    else:
        x_avg_char_width = HALF_WIDTH_12
    flag_wide = flag_35 or flag_36
    xml.find("OS_2/xAvgCharWidth").set("value", str(x_avg_char_width))

    # fsSelectionを編集
    # タグ形式: <fsSelection value="00000000 11000000" />
    # スタイルに応じたビットを立てる
    fs_selection = None
    if style == "Regular":
        fs_selection = "00000001 01000000"
    elif style == "Italic":
        fs_selection = "00000001 00000001"
    elif style == "Bold":
        fs_selection = "00000001 00100000"
    elif style == "BoldItalic":
        fs_selection = "00000001 00100001"

    if fs_selection is not None:
        xml.find("OS_2/fsSelection").set("value", fs_selection)

    # panoseを編集
    # タグ形式:
    # <panose>
    #   <bFamilyType value="2" />
    #   <bSerifStyle value="11" />
    #   <bWeight value="6" />
    #   <bProportion value="9" />
    #   <bContrast value="6" />
    #   <bStrokeVariation value="3" />
    #   <bArmStyle value="0" />
    #   <bLetterForm value="2" />
    #   <bMidline value="0" />
    #   <bXHeight value="4" />
    # </panose>
    if style == "Regular" or style == "Italic":
        bWeight = 5
    else:
        bWeight = 8
    if flag_wide:
        panose = {
            "bFamilyType": 2,
            "bSerifStyle": 11,
            "bWeight": bWeight,
            "bProportion": 3,
            "bContrast": 5,
            "bStrokeVariation": 2,
            "bArmStyle": 3,
            "bLetterForm": 0,
            "bMidline": 2,
            "bXHeight": 3,
        }
    else:
        panose = {
            "bFamilyType": 2,
            "bSerifStyle": 11,
            "bWeight": bWeight,
            "bProportion": 9,
            "bContrast": 5,
            "bStrokeVariation": 2,
            "bArmStyle": 3,
            "bLetterForm": 0,
            "bMidline": 2,
            "bXHeight": 3,
        }

    for key, value in panose.items():
        xml.find(f"OS_2/panose/{key}").set("value", str(value))


def fix_post_table(xml: ET, flag_wide):
    """post テーブルを編集する"""
    # isFixedPitchを編集
    # タグ形式: <isFixedPitch value="0"/>
    is_fixed_pitch = 0 if flag_wide else 1
    xml.find("post/isFixedPitch").set("value", str(is_fixed_pitch))


def fix_name_table(xml: ET):
    """name テーブルを編集する
    何故か謎の内容の著作権フィールドが含まれてしまうので、削除する。
    """
    # タグ形式: <namerecord nameID="0" platformID="1" platEncID="0" langID="0x0" unicode="True">COPYLIGHT</namerecord>
    parent = xml.find("name")
    for element in parent.findall("namerecord[@nameID='0']"):
        if FONT_NAME not in element.text:
            parent.remove(element)


if __name__ == "__main__":
    main()
