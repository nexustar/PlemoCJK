#!/usr/bin/env python3
"""Regenerate IBM Plex Sans SC Text weight from the Glyphs master (PlemoCJK).

The IBM-distributed IBM Plex Sans SC Text is interpolated at weight 425,
about 5% thinner than JP/TC Text (450). When the four regional sub-fonts
are placed side by side, SC appears noticeably thinner. This script rebuilds
only the Text weight at interpolation position 450 from the Glyphs master
published by IBM. Other weights use the IBM release as-is.

    Weight          Horizontal stroke of U+4E00 / Vertical stroke of U+4E28
    IBM SC Text (425)   80 / 84
    JP, TC Text (450)   84 / 89
    This script output  84 / 89

Processing steps:

1. Fetch the `sources.zip` attachment from the IBM/plex GitHub release
   (tag `@ibm/plex-sans-sc@X.Y.Z`). URL and SHA-256 are recorded in
   sources.lock for subsequent verification. The zip is cached under
   source/ (not committed to the repository).
2. Extract only the master `sources/masters/IBM Plex Sans SC.glyphs` from the zip.
3. Patch the interpolationWeight of the name="Text" instance from 425 to 450
   (Medium 505 / SemiBold 602 are stale values left in the master; leave them alone).
4. Run fontmake to interpolate only the Text instance into TTF.
5. Align cmap / name / OS/2 etc. with the IBM release of SC Text.
   (fontmake adds U+0302 / U+0303 / U+24C7 which IBM omits from the cmap,
    so remove those; conversely add U+22EF which IBM includes.
    This makes the cmap identical across all 8 SC weights.)
6. Write source/regenerated/IBMPlexSansSC-Text.ttf.

Intermediate files (UFO etc.) can reach several GB, so the work directory is
created under TMPDIR and deleted on exit (use --keep-work to retain it).
fontmake requires several minutes and about 3GB of memory. glyphsLib warnings
about missing kern classes are harmless.

Usage:
    python3 regen_sc_text.py                   # fetch + regenerate (verify sources.lock)
    python3 regen_sc_text.py --update-lock     # resolve release and update sources.lock
    python3 regen_sc_text.py --check           # verify local zip and output only
    python3 regen_sc_text.py --keep-work       # keep intermediate files
    python3 regen_sc_text.py --work-dir DIR    # specify work directory
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

import plemocjk_config

ROOT = Path(__file__).resolve().parent
LOCK_PATH = ROOT / "sources.lock"
# Key used by this script in sources.lock, separate from fetch_sources.py's "files"
LOCK_KEY = "sc_master_source"

RELEASES_API = "https://api.github.com/repos/IBM/plex/releases?per_page=100"
# Observed (2026-09): tag is "@ibm/plex-sans-sc@1.1.0", attachment is sources.zip (186,169,692 B)
RELEASE_TAG_PREFIX = "@ibm/plex-sans-sc@"
ASSET_NAME = "sources.zip"

# Cache filename under source/ (.gitignored)
ZIP_NAME = "ibm-plex-sans-sc-sources.zip"
# Path to the master within the zip. The zip also contains pre-interpolated
# instances under instances/{postscript,truetype}/, but those are still at 425
MASTER_IN_ZIP = "sources/masters/IBM Plex Sans SC.glyphs"

# Target instance to patch
INSTANCE_NAME = "Text"
EXPECTED_WEIGHT = 425
TARGET_WEIGHT = 450
# Value passed to fontmake -i (familyName + styleName)
FONTMAKE_INSTANCE = "IBM Plex Sans SC Text"

REGION = "SC"
STYLE = "Text"
OUT_NAME = f"IBMPlexSans{REGION}-{STYLE}.ttf"

# OS/2 / hhea / post / head fields to align with the IBM release
OS2_FIELDS = (
    "usWidthClass",
    "fsType",
    "fsSelection",
    "achVendID",
    "sTypoAscender",
    "sTypoDescender",
    "sTypoLineGap",
    "usWinAscent",
    "usWinDescent",
    "sxHeight",
    "sCapHeight",
)
HHEA_FIELDS = ("ascender", "descender", "lineGap")
POST_FIELDS = ("underlinePosition", "underlineThickness", "isFixedPitch")
HEAD_FIELDS = ("fontRevision", "macStyle")

# Characters for verification: U+4E00 horizontal stroke (measured by height), U+4E28 vertical stroke (measured by width)
STROKE_GLYPHS = ((0x4E00, "height"), (0x4E28, "width"))

CHUNK = 1 << 20


def log(*args) -> None:
    print(*args, flush=True)


# ---------------------------------------------------------------------------
# Release resolution and fetching
# ---------------------------------------------------------------------------
def _version_key(tag: str) -> tuple:
    version = tag[len(RELEASE_TAG_PREFIX) :]
    parts = []
    for item in re.split(r"[.\-+]", version):
        parts.append((0, int(item)) if item.isdigit() else (1, item))
    return tuple(parts)


def resolve_release() -> dict[str, str]:
    """Find the latest plex-sans-sc release and its sources.zip via the GitHub API."""
    request = urllib.request.Request(
        RELEASES_API,
        headers={
            "User-Agent": "PlemoCJK-regen-sc-text",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        releases = json.load(response)

    candidates = [
        release
        for release in releases
        if str(release.get("tag_name", "")).startswith(RELEASE_TAG_PREFIX)
    ]
    if not candidates:
        raise RuntimeError(
            f"{RELEASES_API} に {RELEASE_TAG_PREFIX}* のリリースが見つかりません"
        )
    release = max(candidates, key=lambda r: _version_key(r["tag_name"]))
    for asset in release.get("assets", []):
        if asset.get("name") == ASSET_NAME:
            return {
                "tag": release["tag_name"],
                "asset": asset["name"],
                "url": asset["browser_download_url"],
                "size": str(asset["size"]),
            }
    raise RuntimeError(
        f"リリース {release['tag_name']} に {ASSET_NAME} がありません "
        f"(添付: {[a.get('name') for a in release.get('assets', [])]})"
    )


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def load_lock() -> dict:
    if not LOCK_PATH.is_file():
        return {}
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def save_lock(entry: dict[str, str]) -> None:
    """Replace only the LOCK_KEY entry in sources.lock (preserving fetch_sources.py's records)."""
    lock = load_lock()
    lock[LOCK_KEY] = entry
    LOCK_PATH.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    log(f"wrote {LOCK_PATH.relative_to(ROOT)} [{LOCK_KEY}]")


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(
        url, headers={"User-Agent": "PlemoCJK-regen-sc-text"}
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        with tmp.open("wb") as handle:
            while chunk := response.read(CHUNK):
                handle.write(chunk)
    tmp.replace(dest)


def ensure_sources_zip(
    zip_path: Path, update_lock: bool, check_only: bool, force: bool
) -> dict[str, str]:
    """Prepare sources.zip and verify its SHA-256. Returns the lock entry."""
    entry = dict(load_lock().get(LOCK_KEY, {}))

    if update_lock or not entry.get("url"):
        if check_only:
            raise RuntimeError(
                f"sources.lock に {LOCK_KEY} がありません。"
                "python3 regen_sc_text.py --update-lock を実行してください"
            )
        log("resolving IBM/plex release ...")
        resolved = resolve_release()
        log(f"  tag={resolved['tag']} asset={resolved['asset']}")
        previous = entry.get("url")
        if previous is not None and previous != resolved["url"]:
            # Invalidate cache when URL changes
            zip_path.unlink(missing_ok=True)
        entry.update(resolved)
        entry.pop("sha256", None)

    if force:
        zip_path.unlink(missing_ok=True)

    if not zip_path.is_file():
        if check_only:
            raise RuntimeError(f"{zip_path.relative_to(ROOT)} がありません")
        log(f"download {entry['url']}")
        download(entry["url"], zip_path)

    digest = sha256_of(zip_path)
    expected = entry.get("sha256")
    if expected is None:
        entry["sha256"] = digest
        entry["path"] = zip_path.relative_to(ROOT).as_posix()
        entry["master"] = MASTER_IN_ZIP
        save_lock(entry)
    elif expected != digest:
        raise RuntimeError(
            f"{zip_path.relative_to(ROOT)}: sha256 mismatch\n"
            f"  expected {expected}\n  actual   {digest}\n"
            "  IBM がリリースを差し替えた場合は --update-lock で記録し直してください"
        )
    else:
        log(f"verified {zip_path.relative_to(ROOT)} sha256={digest[:16]}...")
    return entry


def extract_master(zip_path: Path, dest: Path) -> Path:
    """Extract only the master file from the zip."""
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if MASTER_IN_ZIP in names:
            member = MASTER_IN_ZIP
        else:
            matches = [n for n in names if n.endswith(MASTER_IN_ZIP.split("/")[-1])]
            if len(matches) != 1:
                raise RuntimeError(
                    f"{zip_path.name} の中に母版が一意に見つかりません: {matches}\n"
                    f"  zip の内容: {names}"
                )
            member = matches[0]
        info = archive.getinfo(member)
        dest.parent.mkdir(parents=True, exist_ok=True)
        log(f"extract {member} ({info.file_size / 1e6:.0f}MB) -> {dest}")
        with archive.open(info) as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out, CHUNK)
    return dest


# ---------------------------------------------------------------------------
# Patch the instances block in the master source
#
# Fully parsing the 210MB openstep plist would be expensive, so we scan only
# the instances array by tracking bracket nesting.
# interpolationWeight also appears in Medium (505) / SemiBold (602), but those
# are stale values left in the master -- only the Text block is patched.
# ---------------------------------------------------------------------------
_PAIRS = {"(": ")", "{": "}"}


def _skip_string(text: str, index: int) -> int:
    """Return the position of the matching closing quote when text[index] == '\"'."""
    i = index + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return i
        i += 1
    raise ValueError("unterminated string in .glyphs file")


def _match_bracket(text: str, index: int) -> int:
    """Return the position of the matching closing bracket when text[index] is '(' or '{'."""
    stack = [_PAIRS[text[index]]]
    i = index + 1
    while i < len(text):
        char = text[i]
        if char == '"':
            i = _skip_string(text, i)
        elif char in _PAIRS:
            stack.append(_PAIRS[char])
        elif char in (")", "}"):
            if char != stack[-1]:
                raise ValueError(f"mismatched bracket at offset {i}")
            stack.pop()
            if not stack:
                return i
        i += 1
    raise ValueError("unbalanced brackets in .glyphs file")


def _top_level_blocks(text: str, lo: int, hi: int):
    """Yield (start, end) of each depth-0 {...} block within [lo, hi)."""
    i = lo
    while i < hi:
        char = text[i]
        if char == '"':
            i = _skip_string(text, i) + 1
        elif char == "{":
            end = _match_bracket(text, i)
            yield i, end
            i = end + 1
        elif char == "(":
            i = _match_bracket(text, i) + 1
        else:
            i += 1


def _top_level_assignments(text: str, lo: int, hi: int):
    """Yield (key, value_start, value_end) for each depth-0 `key = value;` within [lo, hi)."""
    i = lo
    key_start = lo
    equals = None
    while i < hi:
        char = text[i]
        if char == '"':
            i = _skip_string(text, i) + 1
            continue
        if char in _PAIRS:
            i = _match_bracket(text, i) + 1
            continue
        if char == "=" and equals is None:
            equals = i
        elif char == ";":
            if equals is not None:
                yield text[key_start:equals].strip(), equals + 1, i
            equals = None
            key_start = i + 1
        i += 1


def patch_text_instance(path: Path) -> None:
    """Set the interpolationWeight of the name="Text" instance to TARGET_WEIGHT."""
    text = path.read_text(encoding="utf-8")

    match = re.search(r"(?m)^instances\s*=\s*\(", text)
    if match is None:
        raise RuntimeError(f"{path.name} に instances 配列が見つかりません")
    open_paren = text.index("(", match.start())
    close_paren = _match_bracket(text, open_paren)

    target: tuple[int, int] | None = None
    summary: list[str] = []
    for block_start, block_end in _top_level_blocks(text, open_paren + 1, close_paren):
        fields = {
            key: (value_start, value_end)
            for key, value_start, value_end in _top_level_assignments(
                text, block_start + 1, block_end
            )
        }
        if "name" not in fields:
            continue
        name = text[slice(*fields["name"])].strip().strip('"')
        weight_span = fields.get("interpolationWeight")
        weight = text[slice(*weight_span)].strip() if weight_span else "(default)"
        summary.append(f"{name}={weight}")
        if name != INSTANCE_NAME:
            continue
        if weight_span is None:
            raise RuntimeError(
                f"インスタンス {name} に interpolationWeight がありません"
            )
        if target is not None:
            raise RuntimeError(f"インスタンス {INSTANCE_NAME} が複数あります")
        target = weight_span

    log("  instances: " + "  ".join(summary))
    if target is None:
        raise RuntimeError(f"インスタンス {INSTANCE_NAME} が見つかりません")

    current = text[slice(*target)].strip()
    if current != str(EXPECTED_WEIGHT):
        raise RuntimeError(
            f"{INSTANCE_NAME} の interpolationWeight が {EXPECTED_WEIGHT} ではなく "
            f"{current} でした。IBM が母版を直した可能性があります。"
            "EXPECTED_WEIGHT を確認してください"
        )
    log(
        f"  patch instance {INSTANCE_NAME}: "
        f"interpolationWeight {current} -> {TARGET_WEIGHT}"
    )
    patched = text[: target[0]] + f" {TARGET_WEIGHT}" + text[target[1] :]
    path.write_text(patched, encoding="utf-8")


# ---------------------------------------------------------------------------
# fontmake interpolation
# ---------------------------------------------------------------------------
def run_fontmake(glyphs_path: Path, work_dir: Path) -> Path:
    out_dir = work_dir / "out"
    command = [
        sys.executable,
        "-m",
        "fontmake",
        "-g",
        str(glyphs_path),
        "-i",
        FONTMAKE_INSTANCE,
        "-o",
        "ttf",
        "--overlaps-backend",
        "pathops",
        "--no-production-names",
        "--master-dir",
        str(work_dir / "master_ufo"),
        "--instance-dir",
        str(work_dir / "instance_ufo"),
        "--output-dir",
        str(out_dir),
    ]
    log("  " + " ".join(command))
    log("  (数分かかります。glyphsLib の kern class の警告は無害です)")
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "fontmake を実行できませんでした。pip install 'fontmake[pathops]' を"
            "実行してください"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"fontmake が失敗しました (exit {exc.returncode})") from exc

    produced = sorted(out_dir.glob("*.ttf"))
    if len(produced) != 1:
        raise RuntimeError(f"fontmake の出力が 1 つではありません: {produced}")
    return produced[0]


# ---------------------------------------------------------------------------
# Align with the IBM release
# ---------------------------------------------------------------------------
def align_cmap(font: TTFont, reference: TTFont) -> tuple[list[int], list[int]]:
    """Align the cmap codepoint set with the IBM release.

    fontmake adds codepoints that IBM omits from the cmap
    (U+0302 / U+0303 / U+24C7). Conversely, IBM maps U+22EF to the same glyph
    as U+2026, but fontmake does not produce this mapping.
    If the cmap differs across the 8 SC weights, prepare_cjk.py's fallback fill
    results would vary per weight, so we align them here.

    Glyph names may differ between the release (production names) and the
    regenerated font (--no-production-names), so resolution first tries
    sibling codepoints that map to the same glyph in the release, then
    falls back to name-based lookup.
    """
    current = dict(font.getBestCmap())
    reference_cmap = reference.getBestCmap()
    glyph_names = set(font.getGlyphOrder())

    removed = sorted(set(current) - set(reference_cmap))
    for codepoint in removed:
        del current[codepoint]

    added: list[int] = []
    unresolved: list[int] = []
    for codepoint in sorted(set(reference_cmap) - set(current)):
        reference_name = reference_cmap[codepoint]
        siblings = [
            other
            for other, name in reference_cmap.items()
            if name == reference_name and other in current
        ]
        if siblings:
            current[codepoint] = current[min(siblings)]
        elif reference_name in glyph_names:
            current[codepoint] = reference_name
        else:
            unresolved.append(codepoint)
            continue
        added.append(codepoint)

    if unresolved:
        raise RuntimeError(
            "発布件にあって再生成フォントで解決できないコードポイント: "
            + ", ".join(f"U+{cp:04X}" for cp in unresolved)
        )

    bmp = {cp: name for cp, name in current.items() if cp <= 0xFFFF}
    tables = []
    for platform_id, plat_enc_id, fmt, mapping in (
        (0, 3, 4, bmp),
        (0, 4, 12, current),
        (3, 1, 4, bmp),
        (3, 10, 12, current),
    ):
        subtable = CmapSubtable.newSubtable(fmt)
        subtable.platformID = platform_id
        subtable.platEncID = plat_enc_id
        subtable.language = 0
        subtable.cmap = dict(mapping)
        tables.append(subtable)
    font["cmap"].tableVersion = 0
    font["cmap"].tables = tables
    return removed, added


def align_names(font: TTFont, reference: TTFont) -> None:
    """Replace nameIDs 255 and below with those from the IBM release.

    nameIDs 256+ are referenced by GSUB FeatureParams (e.g. stylistic set
    display names), so they are kept from the regenerated font.
    """
    kept = [record for record in font["name"].names if record.nameID >= 256]
    copied = [record for record in reference["name"].names if record.nameID < 256]
    font["name"].names = sorted(
        copied + kept,
        key=lambda r: (r.nameID, r.platformID, r.platEncID, r.langID),
    )


def align_tables(font: TTFont, reference: TTFont) -> list[str]:
    """Align OS/2 / hhea / post / head numeric values with the IBM release."""
    changed = []
    for tag, fields in (
        ("OS/2", OS2_FIELDS),
        ("hhea", HHEA_FIELDS),
        ("post", POST_FIELDS),
        ("head", HEAD_FIELDS),
    ):
        for field in fields:
            want = getattr(reference[tag], field)
            if getattr(font[tag], field) != want:
                changed.append(f"{tag}.{field}")
            setattr(font[tag], field, want)
    # panose is a sub-structure, so replace it as a whole
    if font["OS/2"].panose.__dict__ != reference["OS/2"].panose.__dict__:
        changed.append("OS/2.panose")
    font["OS/2"].panose = reference["OS/2"].panose
    return changed


def measure_strokes(path: Path) -> dict[int, float | None]:
    font = TTFont(path, lazy=True)
    try:
        cmap = font.getBestCmap()
        glyph_set = font.getGlyphSet()
        result: dict[int, float | None] = {}
        for codepoint, axis in STROKE_GLYPHS:
            name = cmap.get(codepoint)
            if name is None:
                result[codepoint] = None
                continue
            pen = BoundsPen(glyph_set)
            glyph_set[name].draw(pen)
            if pen.bounds is None:
                result[codepoint] = None
                continue
            x_min, y_min, x_max, y_max = pen.bounds
            result[codepoint] = y_max - y_min if axis == "height" else x_max - x_min
        return result
    finally:
        font.close()


def finalize(raw: Path, reference_path: Path, out_path: Path) -> None:
    log(f"  align with {reference_path.relative_to(ROOT)}")
    font = TTFont(raw, recalcBBoxes=False, recalcTimestamp=False)
    reference = TTFont(reference_path, lazy=True)

    if font["head"].unitsPerEm != reference["head"].unitsPerEm:
        raise RuntimeError(
            f"unitsPerEm が違います: {font['head'].unitsPerEm} != "
            f"{reference['head'].unitsPerEm}"
        )
    if reference["OS/2"].usWeightClass != TARGET_WEIGHT:
        raise RuntimeError(
            f"発布件の usWeightClass が {TARGET_WEIGHT} ではありません: "
            f"{reference['OS/2'].usWeightClass}"
        )

    removed, added = align_cmap(font, reference)
    log(
        f"  cmap: -{len(removed)} "
        f"[{', '.join(f'U+{cp:04X}' for cp in removed)}] "
        f"+{len(added)} [{', '.join(f'U+{cp:04X}' for cp in added)}] "
        f"-> {len(font.getBestCmap())} codepoints"
    )
    align_names(font, reference)
    changed = align_tables(font, reference)
    font["OS/2"].usWeightClass = TARGET_WEIGHT
    log(f"  aligned fields: {', '.join(changed) if changed else '(none)'}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    font.save(out_path)
    font.close()
    reference.close()
    log(f"  wrote {out_path.relative_to(ROOT)} ({out_path.stat().st_size / 1e6:.1f}MB)")


def verify(config: plemocjk_config.Config, out_path: Path) -> int:
    """Verify that stroke widths of U+4E00/U+4E28 and cmap match other regions and weights."""
    errors = 0
    log("--- verification ---")

    measures = {f"{REGION} {STYLE} (regenerated)": measure_strokes(out_path)}
    for region in config.regions:
        path = config.release_source_path(region, STYLE)
        if path.is_file():
            measures[f"{region} {STYLE} (IBM release)"] = measure_strokes(path)

    for label, values in measures.items():
        detail = "  ".join(
            f"U+{cp:04X}={'n/a' if values[cp] is None else format(values[cp], '.0f')}"
            for cp, _ in STROKE_GLYPHS
        )
        log(f"  {label}: {detail}")

    for codepoint, _ in STROKE_GLYPHS:
        wanted: dict[str, float] = {}
        for label, values in measures.items():
            if "IBM release" in label and label.startswith(REGION):
                continue  # exclude the font being replaced from comparison
            if values[codepoint] is not None:
                wanted[label] = values[codepoint]
        if len(wanted) < 2:
            continue
        lowest, highest = min(wanted.values()), max(wanted.values())
        if lowest != highest:
            log(
                f"  U+{codepoint:04X}: 地域間で一致しません "
                + ", ".join(f"{k}={v:.0f}" for k, v in wanted.items())
            )
            errors += 1
        else:
            log(f"  U+{codepoint:04X}: all {highest:.0f} OK")

    reference_cmaps: dict[str, set[int]] = {}
    for style in plemocjk_config.UPRIGHT_STYLES:
        path = config.release_source_path(REGION, style)
        if style == STYLE:
            path = out_path
        if not path.is_file():
            continue
        font = TTFont(path, lazy=True)
        reference_cmaps[style] = set(font.getBestCmap())
        font.close()
    sizes = {style: len(cps) for style, cps in reference_cmaps.items()}
    log(f"  {REGION} cmap sizes: {sizes}")
    regular = reference_cmaps.get("Regular")
    if regular is not None and reference_cmaps.get(STYLE) != regular:
        difference = reference_cmaps[STYLE] ^ regular
        log(
            f"  {STYLE} の cmap が Regular と違います: "
            + ", ".join(f"U+{cp:04X}" for cp in sorted(difference))
        )
        errors += 1
    elif regular is not None:
        log(f"  {STYLE} cmap == {REGION} Regular cmap OK")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-lock",
        action="store_true",
        help="GitHub API でリリースを解決し sources.lock を更新する",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="ダウンロードも再生成もせず、手元の zip と出力を検証する",
    )
    parser.add_argument(
        "--force", action="store_true", help="キャッシュ済みの zip を再取得する"
    )
    parser.add_argument(
        "--work-dir",
        default=None,
        help="中間生成物の置き場所 (既定: TMPDIR 以下の一時ディレクトリ)",
    )
    parser.add_argument(
        "--keep-work", action="store_true", help="中間生成物を消さない"
    )
    parser.add_argument(
        "--out",
        default=None,
        help=f"出力先 (既定: build.ini の REGENERATED_FONT から決まる {OUT_NAME})",
    )
    args = parser.parse_args()

    config = plemocjk_config.load()
    out_path = (
        Path(args.out) if args.out else config.regenerated_path(REGION, STYLE)
    )
    reference_path = config.release_source_path(REGION, STYLE)

    zip_path = config.source_dir / ZIP_NAME
    try:
        ensure_sources_zip(zip_path, args.update_lock, args.check, args.force)
    except Exception as exc:  # noqa: BLE001 - only the message matters for user display
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not reference_path.is_file():
        print(
            f"ERROR: 発布件 {reference_path.relative_to(ROOT)} がありません。\n"
            "  python3 fetch_sources.py --regions SC を先に実行してください",
            file=sys.stderr,
        )
        return 1

    if args.check:
        if not out_path.is_file():
            print(
                f"ERROR: {out_path.relative_to(ROOT)} がありません。"
                "python3 regen_sc_text.py を実行してください",
                file=sys.stderr,
            )
            return 1
        return 1 if verify(config, out_path) else 0

    work_dir = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(
        prefix="plemocjk-regen-"
    ))
    work_dir.mkdir(parents=True, exist_ok=True)
    log(f"work dir: {work_dir}")
    try:
        glyphs_path = work_dir / MASTER_IN_ZIP.split("/")[-1]
        if not glyphs_path.is_file():
            extract_master(zip_path, glyphs_path)
        log("patching the master source")
        patch_text_instance(glyphs_path)
        log("running fontmake")
        raw = run_fontmake(glyphs_path, work_dir)
        # The master (210MB) is no longer needed; delete it early to free space
        glyphs_path.unlink(missing_ok=True)
        log("finalizing")
        finalize(raw, reference_path, out_path)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.keep_work:
            log(f"kept work dir: {work_dir}")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)

    return 1 if verify(config, out_path) else 0


if __name__ == "__main__":
    raise SystemExit(main())
