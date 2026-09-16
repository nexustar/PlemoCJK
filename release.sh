#!/usr/bin/env bash
# Organize TTF / TTC output in build/ into per-region directories and create zip archives
#
# Distribution units (by region):
#   PlemoCJK-SC_{VERSION}.zip     SC region (all variants)
#   PlemoCJK-TC_{VERSION}.zip     TC region
#   PlemoCJK-JP_{VERSION}.zip     JP region
#   PlemoCJK-KR_{VERSION}.zip     KR region
#   PlemoCJK-TTC_{VERSION}.zip    TTC bundling all 4 regions into a single file
#
# Required commands: zip / unzip (used to create archives and verify contents)
#
# Environment variables:
#   VARIANTS / REGIONS  Limit scope (default: everything in build/)
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
    echo "ERROR: could not read VERSION / FONT_NAME from build.ini" >&2
    exit 1
fi

# External commands are used to create and verify zip archives.
# They are not included in the composite-font-builder image used for font generation,
# so release packaging must run on the host or in a container with zip / unzip installed.
missing_tools=()
for tool in zip unzip; do
    command -v "$tool" >/dev/null 2>&1 || missing_tools+=("$tool")
done
if [ ${#missing_tools[@]} -ne 0 ]; then
    echo "ERROR: required command(s) not found: ${missing_tools[*]}" >&2
    echo "  Debian/Ubuntu: sudo apt-get install -y zip unzip" >&2
    echo "  (The font build image does not include zip/unzip;" >&2
    echo "   run release.sh on the host instead)" >&2
    exit 1
fi

release_dir="${BUILD_DIR}/release"

# Build the distribution manifest from the files actually present in build/.
# One line per entry: "package_dir<TAB>family_dir<TAB>filename"
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
    plemocjk_config.VARIANTS
)


rows = []
for variant in variants:
    if variant not in plemocjk_config.VARIANTS:
        continue
    bare = plemocjk_config.VARIANTS[variant].label
    for region in regions:
        tag = config.variant_tag(variant, region)
        htag = plemocjk_config.hyphenate_tag(tag)
        for style in plemocjk_config.ALL_STYLES:
            filename = f"{font_name}-{htag}-{style}.ttf"
            if (build_dir / filename).is_file():
                rows.append(
                    (f"{font_name}-{region}_{version}", f"{font_name}{bare}_{region}", filename)
                )
    hbare = plemocjk_config.hyphenate_tag(bare)
    for style in plemocjk_config.ALL_STYLES:
        stem = f"{font_name}-{hbare}" if hbare else font_name
        filename = f"{stem}-{style}.ttc"
        if (build_dir / "ttc" / filename).is_file():
            rows.append(
                (f"{font_name}-TTC_{version}", f"{font_name}{bare}_TTC", filename)
            )

for row in sorted(set(rows)):
    print("\t".join(row))
PYTHON

if [ ! -s "$manifest" ]; then
    echo "ERROR: no distributable fonts found in ${BUILD_DIR}/." \
        "Run make.sh first" >&2
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
for dir in "${release_dir}/${FONT_NAME}"-*; do
    [ -d "$dir" ] || continue
    name="$(basename "$dir")"
    echo "zip: ${name}.zip"
    (cd "$release_dir" && zip -r -q "${name}.zip" "$name")
done

echo "### Checking release layout ###"
check_fail=0

# Verify that all entries in the manifest are present
while IFS=$'\t' read -r package_dir family_dir filename; do
    if [ ! -f "${release_dir}/${package_dir}/${family_dir}/${filename}" ]; then
        echo "MISSING: ${package_dir}/${family_dir}/${filename}" >&2
        check_fail=1
    fi
done <"$manifest"

# Check for unexpected files
expected_list="$(mktemp)"
actual_list="$(mktemp)"
cut -f1,2,3 "$manifest" | awk -F'\t' '{print $1"/"$2"/"$3}' | sort >"$expected_list"
(
    cd "$release_dir"
    find . -type f \( -name '*.ttf' -o -name '*.ttc' \) | sed 's#^\./##' | sort
) >"$actual_list"
if ! cmp -s "$expected_list" "$actual_list"; then
    echo "ERROR: distribution manifest does not match output files" >&2
    diff -u "$expected_list" "$actual_list" >&2 || true
    check_fail=1
fi

# Verify that zip contents match the directory
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
        echo "ERROR: ${package_dir}.zip contents do not match directory" >&2
        diff -u "$dir_tmp" "$zip_tmp" >&2 || true
        check_fail=1
    fi
    rm -f "$zip_tmp" "$dir_tmp"
done
rm -f "$expected_list" "$actual_list"

if ((check_fail != 0)); then
    echo "ERROR: distribution manifest consistency check failed" >&2
    exit 1
fi

echo "### Done ###"
echo "release directory: ${release_dir}"
ls -1 "${release_dir}"/*.zip 2>/dev/null || true
