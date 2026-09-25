"""Regression checks for complete webfont coverage and CSS slice priority."""
import json
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

import subset_webfont as webfont


class WebfontTests(unittest.TestCase):
    def test_last_rule_priority_and_supplemental_coverage(self):
        points = {32, 65, 66, 0x4E00} | set(range(0x20000, 0x20201))
        groups = webfont.plan_slices(points, ["U+41,U+4E00", "U+42", "U+20-7F"])
        self.assertEqual(groups[:2], [{0x4E00}, {32, 65, 66}])
        self.assertEqual([len(g) for g in groups[2:]], [256, 256, 1])
        self.assertEqual(set.union(*groups), points)
        self.assertEqual(sum(map(len, groups)), len(points))
        for group in groups:
            self.assertEqual(webfont.parse_codepoints(webfont.format_codepoints(group)), group)

    def test_missing_region_fails_before_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "PlemoCJK-SC-Regular.ttf").touch()
            with patch("sys.argv", ["subset_webfont.py", tmp]), \
                 patch.object(webfont, "process_region") as process:
                with self.assertRaisesRegex(SystemExit, "TC, JP, KR"):
                    webfont.main()
                process.assert_not_called()

    def make_font(self, path, weight=400, italic=False):
        builder = FontBuilder(1000, isTTF=True)
        names = [".notdef", "space", "A", "han", "extra"]
        builder.setupGlyphOrder(names)
        builder.setupCharacterMap({32: "space", 65: "A", 0x4E00: "han", 0x20000: "extra"})
        glyphs = {}
        for name in names:
            pen = TTGlyphPen(None)
            if name != "space":
                pen.moveTo((0, 0))
                pen.lineTo((200, 0))
                pen.lineTo((100, 500))
                pen.closePath()
            glyphs[name] = pen.glyph()
        builder.setupGlyf(glyphs)
        builder.setupHorizontalMetrics({name: (500, 0) for name in names})
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupNameTable({"familyName": "PlemoCJK SC", "styleName": "Regular"})
        builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWeightClass=weight, fsSelection=1 if italic else 0)
        builder.font["head"].macStyle = 2 if italic else 0
        builder.setupPost()
        builder.save(path)

    def test_real_woff2_css_coverage_and_stale_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ttf = root / "PlemoCJK-SC-Regular.ttf"
            self.make_font(ttf)
            webfont_dir = root / "webfonts"
            out = webfont_dir / "SC"
            out.mkdir(parents=True)
            stale = out / "PlemoCJK-SC-Regular.999.woff2"
            stale.write_bytes(b"obsolete")
            legacy_css = out / "PlemoCJK-SC-Regular.css"
            legacy_css.write_text("old CSS")
            old_bold = out / "PlemoCJK-SC-Bold.1.woff2"
            old_bold.write_bytes(b"old weight")
            unrelated = out / "other.woff2"
            unrelated.write_bytes(b"keep")
            old_css = out / "PlemoCJK-SC.css"
            old_css.write_text("CSS from the old layout")
            with patch.object(webfont, "load_slices", return_value=["U+41,U+4E00", "U+20-7F"]):
                webfont.process_region("SC", [ttf], webfont_dir, "PlemoCJK")
            css = (webfont_dir / "PlemoCJK-SC.css").read_text()
            self.assertIn("font-family: 'PlemoCJK SC'", css)
            self.assertIn("url('SC/PlemoCJK-SC-Regular.1.woff2')", css)
            ranges = webfont.parse_unicode_ranges(css)
            self.assertEqual(len(ranges), 3)
            covered = set()
            for i, value in enumerate(ranges, 1):
                with TTFont(out / f"PlemoCJK-SC-Regular.{i}.woff2") as font:
                    actual = set(font.getBestCmap())
                self.assertEqual(actual, webfont.parse_codepoints(value))
                covered.update(actual)
            self.assertEqual(covered, {32, 65, 0x4E00, 0x20000})
            self.assertFalse(stale.exists())
            self.assertFalse(legacy_css.exists())
            self.assertFalse(old_css.exists())
            self.assertFalse(old_bold.exists())
            self.assertEqual(unrelated.read_bytes(), b"keep")

    def test_all_weights_and_italics_in_regional_css(self):
        weights = dict(zip(webfont.ALL_STYLES[:8], [100, 200, 300, 400, 450, 500, 600, 700]))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = set()
            for style in webfont.ALL_STYLES:
                upright = style.removesuffix("Italic") or "Regular"
                weight, italic = weights[upright], "Italic" in style
                expected.add((weight, "italic" if italic else "normal"))
                for region in webfont.REGION_TO_GOOGLE_FONT:
                    self.make_font(root / f"PlemoCJK-{region}-{style}.ttf", weight, italic)
            self.make_font(root / "PlemoCJK-Term-SC-Bold.ttf", 700)
            with patch("sys.argv", ["subset_webfont.py", str(root)]), \
                 patch.object(webfont, "load_slices", return_value=["U+41,U+4E00", "U+20-7F"]):
                webfont.main()
            version = webfont.read_ini()["version"]
            webfont_dir = root / "release" / f"PlemoCJK_webfont_{version}"
            for name in ["LICENSE", "licenses/LICENSE_IBM-Plex", "licenses/LICENSE_Hack",
                         "README.md", ".nojekyll"]:
                self.assertTrue((webfont_dir / name).exists(), name)
            manifest = json.loads((webfont_dir / "manifest.json").read_text())
            for region, fonts in manifest["regions"].items():
                self.assertEqual(len(fonts), len(webfont.ALL_STYLES))
                for entry in fonts:
                    for item in entry["files"]:
                        path = webfont_dir / item["file"]
                        self.assertEqual(webfont.sha256(path), item["sha256"])
            for region in webfont.REGION_TO_GOOGLE_FONT:
                out = webfont_dir / region
                css = (webfont_dir / f"PlemoCJK-{region}.css").read_text()
                found = set()
                covered = {}
                for block in re.findall(r"@font-face\s*\{([^}]+)\}", css):
                    weight = int(re.search(r"font-weight: (\d+)", block)[1])
                    style = re.search(r"font-style: (\w+)", block)[1]
                    found.add((weight, style))
                    name = re.search(r"url\('([^']+)'\)", block)[1]
                    with TTFont(webfont_dir / name) as font:
                        self.assertEqual(font["OS/2"].usWeightClass, weight)
                        self.assertEqual(bool(font["OS/2"].fsSelection & 1), style == "italic")
                        points = set(font.getBestCmap())
                        self.assertEqual(points, webfont.parse_codepoints(webfont.parse_unicode_ranges(block)[0]))
                        covered.setdefault((weight, style), set()).update(points)
                self.assertEqual(found, expected)
                self.assertEqual(len(list(out.glob("*.woff2"))), 48)
                for points in covered.values():
                    self.assertEqual(points, {32, 65, 0x4E00, 0x20000})

    def test_split_ascii_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            ttf = Path(tmp) / "PlemoCJK-SC-Regular.ttf"
            self.make_font(ttf)
            with patch.object(webfont, "load_slices", return_value=["U+20-40", "U+41-7F"]):
                with self.assertRaisesRegex(RuntimeError, "ASCII split"):
                    webfont.process_region("SC", [ttf], Path(tmp), "PlemoCJK")

    def test_conversion_failure_preserves_existing_output(self):
        for pool in (None, ThreadPoolExecutor(2)):
            with self.subTest(pool=pool), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                regular = root / "PlemoCJK-SC-Regular.ttf"
                bold = root / "PlemoCJK-SC-Bold.ttf"
                self.make_font(regular)
                self.make_font(bold, 700)
                out = root / "webfonts"
                out.mkdir()
                css = out / "PlemoCJK-SC.css"
                css.write_text("previous CSS")
                original_subset = webfont.subset_font

                def fail_on_bold(source, dest, points):
                    if source == bold:
                        raise RuntimeError("conversion failed")
                    original_subset(source, dest, points)

                with patch.object(webfont, "load_slices", return_value=["U+20-7F"]), \
                     patch.object(webfont, "subset_font", side_effect=fail_on_bold):
                    with self.assertRaisesRegex(RuntimeError, "conversion failed"):
                        webfont.process_region("SC", [regular, bold], out, "PlemoCJK", pool)
                self.assertEqual(css.read_text(), "previous CSS")
                self.assertEqual(list(out.iterdir()), [css])
            if pool:
                pool.shutdown()

if __name__ == "__main__":
    unittest.main()
