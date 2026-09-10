#!/usr/bin/env node
// PlemoCJK: 4 地域のサブフォントを 1 つの TTC にまとめる。
//
// otb-ttc-bundle -x (sparse glyph sharing) を使う。-x は字形の内容ハッシュで
// サブフォント間の glyph を突き合わせ、glyf を 1 本にまとめたうえで各サブフォントの
// loca をその部分列にする。fontTools の TTCollection.save(shareTables=True) は
// テーブル単位の完全一致しか見ないので、この圧縮はできない。
//
// 前提 (崩れると共有率が落ちる):
//   - TrueType アウトライン
//   - 全サブフォントで UPM が同じ
//   - 同じ字形が必ず同じバイト列になること (ハングルは 4 地域とも IBM Plex Sans KR
//     由来で同じ処理を通るので一致する)
//
// Usage:
//   node bundle_ttc.mjs                       # build/ の全バリアント x 全スタイル
//   node bundle_ttc.mjs --variant Console     # バリアントを絞る
//   node bundle_ttc.mjs --style Regular
//   node bundle_ttc.mjs --out-dir build/ttc
//   node bundle_ttc.mjs --dry-run
//
// メモリ: 1 組 4 ファイル x 約 13MB でも ot-builder の中間表現は数 GB になるため、
// package.json の npm script は --max-old-space-size=8192 を付けている。

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
      // 継続行 (configparser と同じ扱い)
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

// build.ini の修飾子テンプレートと同じ規則 (plemocjk_config.VARIANT_TABLE)
const VARIANT_TAGS = {
  default: "{R}",
  35: "35{R}",
  Console: "{R}Console",
  "35Console": "35{R}Console",
  ConsoleNF: "{R}ConsoleNF",
  "35ConsoleNF": "35{R}ConsoleNF",
  HS: "{R}HS",
  "35HS": "35{R}HS",
  ConsoleHS: "{R}ConsoleHS",
  "35ConsoleHS": "35{R}ConsoleHS",
};

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
  // TTC に入れる順序は build.ini の [build] TTC_ORDER で決める (決定的にするため)
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
    // TTC のファイル名は地域を含まない (中に 4 地域が入るため)
    const ttcVariant = template.replace("{R}", "");
    for (const style of styles) {
      const inputs = regions.map((region) =>
        path.join(
          buildDir,
          `${fontName}${template.replace("{R}", region)}-${style}.ttf`,
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

      const output = path.join(outDir, `${fontName}${ttcVariant}-${style}.ttc`);
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
        // ot-builder は 4 x 5 万グリフで数 GB 使うので広めに取る
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
