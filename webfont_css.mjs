#!/usr/bin/env node
// PlemoCJK: Print one stylesheet for a chosen set of styles of this npm package.
//
// Shipped as the `bin` of every webfont package (see npm_packages.py). Rules
// are interleaved slice by slice, like the package's default stylesheet, so
// that the same unicode-range repeats within gzip's 32 KB window. Slices of
// one style keep their order, which is what decides range priority.
//
// Usage:
//   npx plemocjk-sc Regular Bold Light > PlemoCJK-SC-subset.css
//
// URLs stay relative: keep the output next to the package's slice directory.

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const prefix = pkg.main.replace(/\.css$/, "") + "-";
const styles = readdirSync(root)
  .filter((name) => name.startsWith(prefix) && name.endsWith(".css"))
  .map((name) => name.slice(prefix.length, -".css".length));

const args = process.argv.slice(2);
if (!args.length || args.some((arg) => arg.startsWith("-"))) {
  console.error(`Usage: npx ${pkg.name} STYLE... > subset.css\nStyles: ${styles.join(", ")}`);
  process.exit(args.includes("--help") || args.includes("-h") ? 0 : 1);
}

const chosen = [...new Set(args.map((arg) => {
  const style = styles.find((s) => s.toLowerCase() === arg.toLowerCase());
  if (!style) {
    console.error(`Unknown style: ${arg}\nStyles: ${styles.join(", ")}`);
    process.exit(1);
  }
  return style;
}))];

const index = (rule) => Number(rule.match(/^\/\* (\d+) \*\//)[1]);
const rules = chosen.flatMap((style) =>
  readFileSync(join(root, `${prefix}${style}.css`), "utf8").trim().split("\n\n"));
process.stdout.write(rules.sort((a, b) => index(a) - index(b)).join("\n\n") + "\n");
