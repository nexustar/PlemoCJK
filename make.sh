#!/usr/bin/env bash
# PlemoCJK: Build per-region subfonts (SC / TC / JP / KR)
#
# Environment variables:
#   DEBUG=1          Build Console Regular for one region only (default: first in REGIONS)
#   REGIONS="SC KR"  Limit regions to build (default: [regions] REGIONS in build.ini)
#   VARIANTS="Console ConsoleNF"  Specify variants directly
#   STYLES="Text TextItalic"      Specify styles (weights) directly
#   SKIP_PREPARE=1   Skip prepare_cjk.py (when source/prepared already exists)
#   MAX_PARALLEL=4   Parallelism level
set -euo pipefail

MAX_PARALLEL="${MAX_PARALLEL:-4}"
DEBUG_OPTS=""
STYLE_OPTS=""

# Same 16 styles as STYLE_TABLE in fontforge_script.py
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
    echo "ERROR: could not read FONT_NAME from build.ini" >&2
    exit 1
fi

# Region and variant lists come from build.ini via plemocjk_config.py
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
print(' '.join(config.default_variants))")"
fi

if [ "${DEBUG:-0}" = "1" ]; then
    # Generate Regular weight only.
    # If VARIANTS / REGIONS are not explicitly set, build only Term x first region.
    echo "### Debug Mode ###"
    DEBUG_OPTS="--debug"
    styles=(Regular)
    if [ -z "${VARIANTS:-}" ]; then
        VARIANT_LIST=(Term)
    fi
    if [ -z "${REGIONS:-}" ]; then
        REGION_LIST=("${REGION_LIST[0]}")
    fi
else
    styles=("${ALL_STYLES[@]}")
fi

# Filter styles (weights) via STYLES. Takes priority over DEBUG
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
        echo "ERROR: STYLES contains unrecognized style(s): ${STYLES}" >&2
        echo "  valid values: ${ALL_STYLES[*]}" >&2
        exit 1
    fi
    styles=("${selected_styles[@]}")
    STYLE_OPTS="--styles $(IFS=,; echo "${styles[*]}")"
fi

echo "### PlemoCJK build ###"
echo "regions:  ${REGION_LIST[*]}"
echo "variants: ${VARIANT_LIST[*]}"
echo "styles:   ${styles[*]}"

# Prepare per-region CJK input fonts
if [ "${SKIP_PREPARE:-0}" != "1" ]; then
    echo "### Preparing CJK source fonts ###"
    # CJK weights have no Italic, so strip Italic from the selected styles
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

file_tag() {
    python3 -c "
import plemocjk_config
print(plemocjk_config.hyphenate_tag(plemocjk_config.load().variant_tag('$1', '$2')))"
}

# The alphanumeric side (IBM Plex Mono + Hack) is region-independent,
# so build it once per variant and reuse the same files across all 4 regions.
build_eng() {
    local variant="$1"
    local options tag name_args
    options="$(variant_options "$variant")"
    tag="$(eng_tag "$variant")"
    echo "FontForge (eng): ${variant} [${options}]"
    # shellcheck disable=SC2086
    fontforge -lang=py -script fontforge_script.py \
        --do-not-delete-build-dir --eng-only --variant-name "$tag" ${DEBUG_OPTS} ${STYLE_OPTS} ${options}
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
        --do-not-delete-build-dir --region "${region}" --variant-name "${tag}" \
        ${DEBUG_OPTS} ${STYLE_OPTS} ${options}
    echo "FontTools: ${tag} ${region}"
    python3 fonttools_script.py "${tag}-" "${region}"
}

fail=0

# Phase 1: alphanumeric side. Lightweight, so sequential is fine. Required before region jobs.
for variant in "${VARIANT_LIST[@]}"; do
    build_eng "$variant" || fail=1
done
if (( fail != 0 )); then
    echo "ERROR: alphanumeric-side build failed" >&2
    exit 1
fi

# Phase 2: run region x variant in parallel
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
    echo "ERROR: build job failed" >&2
    exit 1
fi

# Clean up intermediate alphanumeric-side files that were shared across regions
find "$BUILD_DIR" -maxdepth 1 -name "${FONTFORGE_PREFIX}*" -delete

echo "### Checking generated fonts ###"
missing=0
expected_files=()

for variant in "${VARIANT_LIST[@]}"; do
    for region in "${REGION_LIST[@]}"; do
        ftag="$(file_tag "$variant" "$region")"
        for style in "${styles[@]}"; do
            filename="${FONT_NAME}-${ftag}-${style}.ttf"
            expected_files+=("$filename")
            if [ ! -f "${BUILD_DIR}/${filename}" ]; then
                echo "MISSING: ${BUILD_DIR}/${filename}" >&2
                missing=1
            fi
        done
    done
done

shopt -s nullglob
actual_files=("${BUILD_DIR}/${FONT_NAME}-"*-*.ttf)
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
    echo "ERROR: expected font list does not match actual files" >&2
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
