#!/usr/bin/env bash
# PlemoCJK: 地域別サブフォント (SC / TC / JP / KR) をビルドする
#
# 環境変数:
#   DEBUG=1          Console Regular を 1 地域だけ作る (既定は REGIONS の先頭)
#   REGIONS="SC KR"  作る地域を絞る (既定は build.ini の [regions] REGIONS)
#   VARIANT_SET=full 35 幅版と HS 版も作る (既定は DEFAULT_VARIANTS の 3 つ)
#   VARIANTS="Console ConsoleNF"  バリアントを直接指定する
#   STYLES="Text TextItalic"      スタイル (ウェイト) を直接指定する
#   SKIP_PREPARE=1   prepare_cjk.py を飛ばす (source/prepared が既にある場合)
#   MAX_PARALLEL=4   並列数
set -euo pipefail

MAX_PARALLEL="${MAX_PARALLEL:-4}"
DEBUG_OPTS=""
STYLE_OPTS=""

# fontforge_script.py の STYLE_TABLE と同じ 16 スタイル
ALL_STYLES=(
    Regular Bold Thin ExtraLight Light Text Medium SemiBold
    Italic BoldItalic ThinItalic ExtraLightItalic
    LightItalic TextItalic MediumItalic SemiBoldItalic
)

get_ini() {
    local key="$1"
    local value
    value="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" build.ini | head -1 | cut -d= -f2-)"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

FONT_NAME="$(get_ini FONT_NAME)"
BUILD_DIR="$(get_ini BUILD_FONTS_DIR)"
BUILD_DIR="${BUILD_DIR:-build}"
FONTFORGE_PREFIX="$(get_ini FONTFORGE_PREFIX)"

if [ -z "$FONT_NAME" ]; then
    echo "ERROR: build.ini から FONT_NAME を読めませんでした" >&2
    exit 1
fi

# 地域・バリアントの一覧は build.ini から plemocjk_config.py 経由で取る
read -r -a ALL_REGIONS <<<"$(python3 -c '
import plemocjk_config
print(" ".join(plemocjk_config.load().regions))')"

if [ -n "${REGIONS:-}" ]; then
    read -r -a REGION_LIST <<<"$REGIONS"
else
    REGION_LIST=("${ALL_REGIONS[@]}")
fi

if [ -n "${VARIANTS:-}" ]; then
    read -r -a VARIANT_LIST <<<"$VARIANTS"
else
    read -r -a VARIANT_LIST <<<"$(python3 -c "
import plemocjk_config
config = plemocjk_config.load()
print(' '.join(config.full_variants if '${VARIANT_SET:-default}' == 'full'
               else config.default_variants))")"
fi

if [ "${DEBUG:-0}" = "1" ]; then
    # Regular ウェイトのみ生成する。
    # VARIANTS / REGIONS を明示指定していなければ Console x 先頭地域の 1 ファイルだけにする。
    echo "### Debug Mode ###"
    DEBUG_OPTS="--debug"
    styles=(Regular)
    if [ -z "${VARIANTS:-}" ]; then
        VARIANT_LIST=(Console)
    fi
    if [ -z "${REGIONS:-}" ]; then
        REGION_LIST=("${REGION_LIST[0]}")
    fi
else
    styles=("${ALL_STYLES[@]}")
fi

# STYLES でスタイル (ウェイト) を絞る。DEBUG より優先する
if [ -n "${STYLES:-}" ]; then
    read -r -a wanted_styles <<<"$STYLES"
    selected_styles=()
    for item in "${ALL_STYLES[@]}"; do
        for wanted in "${wanted_styles[@]}"; do
            if [ "$item" = "$wanted" ]; then
                selected_styles+=("$item")
                break
            fi
        done
    done
    if [ ${#selected_styles[@]} -ne ${#wanted_styles[@]} ]; then
        echo "ERROR: STYLES に一致しないスタイルがあります: ${STYLES}" >&2
        echo "  指定できる値: ${ALL_STYLES[*]}" >&2
        exit 1
    fi
    styles=("${selected_styles[@]}")
    STYLE_OPTS="--styles $(IFS=,; echo "${styles[*]}")"
fi

echo "### PlemoCJK build ###"
echo "regions:  ${REGION_LIST[*]}"
echo "variants: ${VARIANT_LIST[*]}"
echo "styles:   ${styles[*]}"

# 地域別の CJK 側入力フォントを用意する
if [ "${SKIP_PREPARE:-0}" != "1" ]; then
    echo "### Preparing CJK source fonts ###"
    # CJK 側のウェイトは Italic を持たないので、選んだスタイルから Italic を外す
    prepare_list=()
    for style in "${styles[@]}"; do
        upright="${style%Italic}"
        upright="${upright:-Regular}"
        if [[ ! " ${prepare_list[*]+"${prepare_list[*]}"} " == *" ${upright} "* ]]; then
            prepare_list+=("$upright")
        fi
    done
    prepare_styles="$(IFS=,; echo "${prepare_list[*]}")"
    python3 prepare_cjk.py \
        --regions "$(IFS=,; echo "${REGION_LIST[*]}")" \
        --styles "$prepare_styles"
fi

mkdir -p "$BUILD_DIR"
find "$BUILD_DIR" -mindepth 1 -delete

variant_options() {
    python3 -c "
import plemocjk_config
print(plemocjk_config.load().variant_options('$1'))"
}

variant_tag() {
    python3 -c "
import plemocjk_config
print(plemocjk_config.load().variant_tag('$1', '$2'))"
}

eng_tag() {
    python3 -c "
import plemocjk_config
print(plemocjk_config.VARIANT_TABLE['$1'][1].replace('{R}', ''))"
}

# 英数字側 (IBM Plex Mono + Hack) は地域に依存しないので、
# バリアントごとに 1 回だけ作り、4 地域で同じファイルを使い回す。
build_eng() {
    local variant="$1"
    local options tag
    options="$(variant_options "$variant")"
    echo "FontForge (eng): ${variant} [${options}]"
    # shellcheck disable=SC2086
    fontforge -lang=py -script fontforge_script.py \
        --do-not-delete-build-dir --eng-only ${DEBUG_OPTS} ${STYLE_OPTS} ${options}
    tag="$(eng_tag "$variant")"
    echo "ttfautohint (eng): ${variant} [${tag}]"
    python3 fonttools_script.py --eng-hint "${tag}-"
}

build_region() {
    local variant="$1"
    local region="$2"
    local options tag
    options="$(variant_options "$variant")"
    tag="$(variant_tag "$variant" "$region")"
    echo "FontForge (cjk): ${variant} ${region} [${options}]"
    # shellcheck disable=SC2086
    fontforge -lang=py -script fontforge_script.py \
        --do-not-delete-build-dir --region "${region}" ${DEBUG_OPTS} ${STYLE_OPTS} ${options}
    echo "FontTools: ${tag} ${region}"
    python3 fonttools_script.py "${tag}-" "${region}"
}

fail=0

# 第 1 段: 英数字側。軽いので逐次で十分。地域ジョブの前提になる。
for variant in "${VARIANT_LIST[@]}"; do
    build_eng "$variant" || fail=1
done
if (( fail != 0 )); then
    echo "ERROR: 英数字側のビルドが失敗しました" >&2
    exit 1
fi

# 第 2 段: 地域 x バリアント を並列で回す
for variant in "${VARIANT_LIST[@]}"; do
    for region in "${REGION_LIST[@]}"; do
        while (( $(jobs -rp | wc -l) >= MAX_PARALLEL )); do
            wait -n || fail=1
        done
        build_region "$variant" "$region" &
    done
done

while (( $(jobs -rp | wc -l) > 0 )); do
    wait -n || fail=1
done

if (( fail != 0 )); then
    echo "ERROR: ビルドジョブが失敗しました" >&2
    exit 1
fi

# 使い回した英数字側の中間ファイルを片付ける
find "$BUILD_DIR" -maxdepth 1 -name "${FONTFORGE_PREFIX}*" -delete

echo "### Checking generated fonts ###"
missing=0
expected_files=()

for variant in "${VARIANT_LIST[@]}"; do
    for region in "${REGION_LIST[@]}"; do
        tag="$(variant_tag "$variant" "$region")"
        for style in "${styles[@]}"; do
            filename="${FONT_NAME}${tag}-${style}.ttf"
            expected_files+=("$filename")
            if [ ! -f "${BUILD_DIR}/${filename}" ]; then
                echo "MISSING: ${BUILD_DIR}/${filename}" >&2
                missing=1
            fi
        done
    done
done

shopt -s nullglob
actual_files=("${BUILD_DIR}/${FONT_NAME}"*-*.ttf)
shopt -u nullglob

declare -A expected_set=()
for filename in "${expected_files[@]}"; do
    expected_set["$filename"]=1
done

unexpected=0
for path in "${actual_files[@]+"${actual_files[@]}"}"; do
    filename="${path##*/}"
    if [ -z "${expected_set[$filename]+x}" ]; then
        echo "UNEXPECTED: ${path}" >&2
        unexpected=1
    fi
done

echo "expected=${#expected_files[@]}  actual=${#actual_files[@]}"
if (( missing != 0 || unexpected != 0 )); then
    echo "ERROR: 生成フォントの一覧と実ファイルが一致しません" >&2
    exit 1
fi

echo "### Checking font readability ###"
check_args=()
for filename in "${expected_files[@]}"; do
    check_args+=("${BUILD_DIR}/${filename}")
done
python3 check_generated_fonts.py "${check_args[@]}"

echo "### Build OK ###"
exit 0
