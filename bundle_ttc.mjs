#!/usr/bin/env node
// PlemoCJK: Bundle 4 regional sub-fonts into a single TTC.
//
// Uses otb-ttc-bundle -x (sparse glyph sharing). -x hashes glyph contents to
// match glyphs across sub-fonts, merging glyf into one table and making each
// sub-font's loca a subsequence of it. fontTools' TTCollection.save(shareTables=True)
// only does table-level exact matching, so it cannot achieve this compression.
//
// Assumptions (sharing ratio degrades if violated):
//   - TrueType outlines
//   - All sub-fonts share the same UPM
//   - Identical glyphs must produce identical byte sequences (Hangul is derived
//     from IBM Plex Sans KR in all 4 regions and goes through the same processing,
//     so they match)
//
// Usage:
//   node bundle_ttc.mjs                       # all variants x all styles in build/
//   node bundle_ttc.mjs --variant Console     # filter by variant
//   node bundle_ttc.mjs --style Regular
//   node bundle_ttc.mjs --out-dir build/ttc
//   node bundle_ttc.mjs --dry-run
//
// Memory: even 4 files x ~13MB can produce multi-GB intermediate representations
// in ot-builder, so the npm script in package.json adds --max-old-space-size=8192.

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const BUNDLER = path.join(
  ROOT,
  "node_modules",
  "otb-ttc-bundle",
  "bin",
  "otb-ttc-bundle",
);

function readIni(file) {
  const text = fs.readFileSync(file, "utf8");
  const result = {};
  let section = "DEFAULT";
  let lastKey = null;
  for (const rawLine of text.split(/\r?\n/)) {
    if (/^\s*[#;]/.test(rawLine) || rawLine.trim() === "") continue;
    const sectionMatch = rawLine.match(/^\s*\[([^\]]+)\]\s*$/);
    if (sectionMatch) {
      section = sectionMatch[1];
      result[section] ??= {};
      lastKey = null;
      continue;
    }
    const kv = rawLine.match(/^(\S[^=]*?)\s*=\s*(.*)$/);
    if (kv) {
      result[section] ??= {};
      lastKey = kv[1].trim();
      result[section][lastKey] = kv[2].trim();
    } else if (lastKey && /^\s+/.test(rawLine)) {
      // continuation line (same handling as Python configparser)
      result[section][lastKey] += " " + rawLine.trim();
    }
  }
  return result;
}

function iniValue(ini, section, key, fallback) {
  return ini[section]?.[key] ?? ini.DEFAULT?.[key] ?? fallback;
}

function splitList(value) {
  return (value ?? "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

function parseArgs(argv) {
  const options = {
    variants: [],
    styles: [],
    outDir: null,
    dryRun: false,
    verbose: false,
    optimize: "-Oz",
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--variant") options.variants.push(argv[++i]);
    else if (arg === "--style") options.styles.push(argv[++i]);
    else if (arg === "--out-dir") options.outDir = argv[++i];
    else if (arg === "--dry-run") options.dryRun = true;
    else if (arg === "--verbose") options.verbose = true;
    else if (arg === "--optimize-speed") options.optimize = "-Op";
    else if (arg === "--optimize-size") options.optimize = "-Oz";
    else {
      console.error(`unknown option: ${arg}`);
      process.exit(2);
    }
  }
  return options;
}

// Modifier templates matching build.ini conventions (plemocjk_config.VARIANT_TABLE)
const VARIANT_TAGS = {
  default: "{R}",
  35: "35{R}",
  Console: "Console{R}",
  "35Console": "35Console{R}",
  ConsoleNF: "ConsoleNF{R}",
  "35ConsoleNF": "35ConsoleNF{R}",
  HS: "HS{R}",
  "35HS": "35HS{R}",
  ConsoleHS: "ConsoleHS{R}",
  "35ConsoleHS": "35ConsoleHS{R}",
  Term: "Term{R}",
};

const REGION_LIST = ["SC", "TC", "JP", "KR"];
const WIDTH_PREFIXES = ["36", "35"];

function hyphenateTag(tag) {
  if (!tag) return tag;
  const parts = [];
  let rest = tag;
  for (const p of WIDTH_PREFIXES) {
    if (rest.startsWith(p)) {
      parts.push(p);
      rest = rest.slice(p.length);
      break;
    }
  }
  let region = "";
  for (const r of REGION_LIST) {
    if (rest.endsWith(r)) {
      region = r;
      rest = rest.slice(0, -r.length);
      break;
    }
  }
  if (rest) parts.push(rest);
  if (region) parts.push(region);
  return parts.join("-");
}

const ALL_STYLES = [
  "Regular",
  "Bold",
  "Thin",
  "ExtraLight",
  "Light",
  "Text",
  "Medium",
  "SemiBold",
  "Italic",
  "BoldItalic",
  "ThinItalic",
  "ExtraLightItalic",
  "LightItalic",
  "TextItalic",
  "MediumItalic",
  "SemiBoldItalic",
];

function main() {
  const options = parseArgs(process.argv.slice(2));

  if (!fs.existsSync(BUNDLER)) {
    console.error(
      `ERROR: ${BUNDLER} が見つかりません。'npm install' を実行してください。`,
    );
    process.exit(1);
  }

  const ini = readIni(path.join(ROOT, "build.ini"));
  const fontName = iniValue(ini, "DEFAULT", "FONT_NAME", "PlemoCJK");
  const buildDir = path.join(
    ROOT,
    iniValue(ini, "DEFAULT", "BUILD_FONTS_DIR", "build"),
  );
  // Sub-font order in TTC is determined by [build] TTC_ORDER in build.ini (for determinism)
  const regions = splitList(iniValue(ini, "build", "TTC_ORDER", "SC, TC, JP, KR"));
  const variants =
    options.variants.length > 0
      ? options.variants
      : splitList(iniValue(ini, "build", "DEFAULT_VARIANTS", "default"));
  const styles = options.styles.length > 0 ? options.styles : ALL_STYLES;
  const outDir = options.outDir
    ? path.resolve(ROOT, options.outDir)
    : path.join(buildDir, "ttc");

  if (!options.dryRun) fs.mkdirSync(outDir, { recursive: true });

  let built = 0;
  let skipped = 0;
  let failed = 0;

  for (const variant of variants) {
    const template = VARIANT_TAGS[variant];
    if (!template) {
      console.error(`ERROR: unknown variant ${variant}`);
      process.exit(2);
    }
    // TTC filename omits the region (the file contains all 4 regions)
    const ttcTag = hyphenateTag(template.replace("{R}", ""));
    for (const style of styles) {
      const inputs = regions.map((region) =>
        path.join(
          buildDir,
          `${fontName}-${hyphenateTag(template.replace("{R}", region))}-${style}.ttf`,
        ),
      );
      const missing = inputs.filter((p) => !fs.existsSync(p));
      if (missing.length > 0) {
        if (missing.length !== inputs.length) {
          console.error(
            `ERROR: ${variant} ${style}: 一部のサブフォントがありません:\n  ` +
              missing.join("\n  "),
          );
          failed++;
        } else {
          skipped++;
        }
        continue;
      }

      const output = path.join(outDir, `${fontName}${ttcTag ? `-${ttcTag}` : ""}-${style}.ttc`);
      const args = ["-x", options.optimize];
      if (options.verbose) args.push("--verbose");
      args.push("-o", output, ...inputs);

      console.log(`bundle ${path.relative(ROOT, output)}`);
      for (const input of inputs) {
        console.log(`    + ${path.basename(input)}`);
      }
      if (options.dryRun) {
        built++;
        continue;
      }

      const result = spawnSync(process.execPath, [BUNDLER, ...args], {
        stdio: "inherit",
        // ot-builder uses several GB for 4 x 50k glyphs, so allocate generously
        env: {
          ...process.env,
          NODE_OPTIONS: `${process.env.NODE_OPTIONS ?? ""} --max-old-space-size=8192`.trim(),
        },
      });
      if (result.status !== 0) {
        console.error(`ERROR: otb-ttc-bundle failed for ${variant} ${style}`);
        failed++;
        continue;
      }
      const inputSize = inputs.reduce((s, p) => s + fs.statSync(p).size, 0);
      const outputSize = fs.statSync(output).size;
      console.log(
        `    ${(outputSize / 1e6).toFixed(1)}MB ` +
          `(inputs ${(inputSize / 1e6).toFixed(1)}MB, ` +
          `${(inputSize / outputSize).toFixed(2)}x)`,
      );
      built++;
    }
  }

  console.log(`built=${built} skipped=${skipped} failed=${failed}`);
  if (failed > 0) process.exit(1);
  if (built === 0) {
    console.error("ERROR: TTC が 1 つも作られませんでした");
    process.exit(1);
  }
}

main();
