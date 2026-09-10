#!/usr/bin/env bash
# build/ に出力された TTF / TTC を地域別ディレクトリに整理し、zip を作成する
#
# 配布の単位:
#   PlemoCJK_{VERSION}.zip        通常版 + Console 版 (地域ごとのディレクトリ)
#   PlemoCJK_NF_{VERSION}.zip     Nerd Fonts 版
#   PlemoCJK_HS_{VERSION}.zip     全角スペース非可視化版 (VARIANT_SET=full のとき)
#   PlemoCJK_TTC_{VERSION}.zip    4 地域を 1 ファイルにまとめた TTC
#
# 必要なコマンド: zip / unzip (zip の作成と中身の検査に使う)
#
# 環境変数:
#   VARIANTS / REGIONS  対象を絞る (既定は build/ にあるものすべて)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

get_ini() {
    local key="$1"
    local value
    value="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" build.ini | head -1 | cut -d= -f2-)"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

VERSION="$(get_ini VERSION)"
FONT_NAME="$(get_ini FONT_NAME)"
BUILD_DIR="$(get_ini BUILD_FONTS_DIR)"
BUILD_DIR="${BUILD_DIR:-build}"

if [ -z "$VERSION" ] || [ -z "$FONT_NAME" ]; then
    echo "ERROR: build.ini から VERSION / FONT_NAME を読めませんでした" >&2
    exit 1
fi

# zip の作成と内容検査に外部コマンドを使う。
# フォント生成に使う composite-font-builder イメージには入っていないので、
# 配布物の作成はホスト側か、zip / unzip を入れたコンテナで実行する。
missing_tools=()
for tool in zip unzip; do
    command -v "$tool" >/dev/null 2>&1 || missing_tools+=("$tool")
done
if [ ${#missing_tools[@]} -ne 0 ]; then
    echo "ERROR: 必要なコマンドがありません: ${missing_tools[*]}" >&2
    echo "  Debian/Ubuntu: sudo apt-get install -y zip unzip" >&2
    echo "  (フォント生成用のビルドイメージには zip/unzip が入っていないため、" >&2
    echo "   release.sh はホスト側で実行してください)" >&2
    exit 1
fi

release_dir="${BUILD_DIR}/release"

# 実際に build/ にあるファイルから配布マニフェストを作る。
# 1 行あたり "package_dir<TAB>family_dir<TAB>filename"
manifest="$(mktemp)"
trap 'rm -f "$manifest"' EXIT

python3 - "$BUILD_DIR" "$VERSION" >"$manifest" <<'PYTHON'
import os
import sys
from pathlib import Path

import plemocjk_config

build_dir = Path(sys.argv[1])
version = sys.argv[2]
config = plemocjk_config.load()
font_name = config.font_name

regions = os.environ.get("REGIONS", "").split() or list(config.regions)
variants = os.environ.get("VARIANTS", "").split() or list(
    plemocjk_config.VARIANT_TABLE
)


def package_of(variant: str) -> str:
    """バリアントをどの配布 zip に入れるか"""
    if "NF" in variant:
        return f"{font_name}_NF_{version}"
    if "HS" in variant:
        return f"{font_name}_HS_{version}"
    return f"{font_name}_{version}"


rows = []
for variant in variants:
    if variant not in plemocjk_config.VARIANT_TABLE:
        continue
    # 地域抜きの修飾子 (ディレクトリ名と TTC のファイル名に使う)
    bare = plemocjk_config.VARIANT_TABLE[variant][1].replace("{R}", "")
    for region in regions:
        tag = config.variant_tag(variant, region)
        for style in plemocjk_config.ALL_STYLES:
            filename = f"{font_name}{tag}-{style}.ttf"
            if (build_dir / filename).is_file():
                rows.append(
                    (package_of(variant), f"{font_name}{bare}_{region}", filename)
                )
    # TTC は地域を含まない 1 ファイル
    for style in plemocjk_config.ALL_STYLES:
        filename = f"{font_name}{bare}-{style}.ttc"
        if (build_dir / "ttc" / filename).is_file():
            rows.append(
                (f"{font_name}_TTC_{version}", f"{font_name}{bare}_TTC", filename)
            )

for row in sorted(set(rows)):
    print("\t".join(row))
PYTHON

if [ ! -s "$manifest" ]; then
    echo "ERROR: ${BUILD_DIR}/ に配布対象のフォントが見つかりません。" \
        "先に make.sh を実行してください" >&2
    exit 1
fi

echo "### Release packaging ###"
echo "VERSION=${VERSION}  FONT_NAME=${FONT_NAME}"
echo "output: ${release_dir}"

rm -rf "$release_dir"
mkdir -p "$release_dir"

copied=0
while IFS=$'\t' read -r package_dir family_dir filename; do
    target="${release_dir}/${package_dir}/${family_dir}"
    mkdir -p "$target"
    case "$filename" in
    *.ttc) source_path="${BUILD_DIR}/ttc/${filename}" ;;
    *) source_path="${BUILD_DIR}/${filename}" ;;
    esac
    cp "$source_path" "${target}/${filename}"
    copied=$((copied + 1))
done <"$manifest"
echo "copied ${copied} files"

echo "### Creating zip archives ###"
for dir in "${release_dir}/${FONT_NAME}"_*; do
    [ -d "$dir" ] || continue
    name="$(basename "$dir")"
    echo "zip: ${name}.zip"
    (cd "$release_dir" && zip -r -q "${name}.zip" "$name")
done

echo "### Checking release layout ###"
check_fail=0

# マニフェストにあるものが全部置かれているか
while IFS=$'\t' read -r package_dir family_dir filename; do
    if [ ! -f "${release_dir}/${package_dir}/${family_dir}/${filename}" ]; then
        echo "MISSING: ${package_dir}/${family_dir}/${filename}" >&2
        check_fail=1
    fi
done <"$manifest"

# 余分なファイルが無いか
expected_list="$(mktemp)"
actual_list="$(mktemp)"
cut -f1,2,3 "$manifest" | awk -F'\t' '{print $1"/"$2"/"$3}' | sort >"$expected_list"
(
    cd "$release_dir"
    find . -type f \( -name '*.ttf' -o -name '*.ttc' \) | sed 's#^\./##' | sort
) >"$actual_list"
if ! cmp -s "$expected_list" "$actual_list"; then
    echo "ERROR: 配布一覧と出力ファイルが一致しません" >&2
    diff -u "$expected_list" "$actual_list" >&2 || true
    check_fail=1
fi

# zip の中身がディレクトリと一致するか
for zip_path in "${release_dir}"/*.zip; do
    [ -f "$zip_path" ] || continue
    package_dir="$(basename "${zip_path%.zip}")"
    zip_tmp="$(mktemp)"
    dir_tmp="$(mktemp)"
    unzip -Z1 "$zip_path" | grep -E '\.(ttf|ttc)$' | sort >"$zip_tmp"
    (
        cd "$release_dir"
        find "$package_dir" -type f \( -name '*.ttf' -o -name '*.ttc' \) | sort
    ) >"$dir_tmp"
    if ! cmp -s "$zip_tmp" "$dir_tmp"; then
        echo "ERROR: ${package_dir}.zip の内容がディレクトリと一致しません" >&2
        diff -u "$dir_tmp" "$zip_tmp" >&2 || true
        check_fail=1
    fi
    rm -f "$zip_tmp" "$dir_tmp"
done
rm -f "$expected_list" "$actual_list"

if ((check_fail != 0)); then
    echo "ERROR: 配布一覧と出力ファイルの整合性チェックに失敗しました" >&2
    exit 1
fi

echo "### Done ###"
echo "release directory: ${release_dir}"
ls -1 "${release_dir}"/*.zip 2>/dev/null || true
