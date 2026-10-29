import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

// index.html asks Google Fonts for Inter by weight, and every weight listed is
// a font file a first visit downloads before the text settles. It listed 800
// and 900, which nothing in the app uses. This keeps the list and the code in
// step both ways: no weight fetched for nothing, none used and not fetched
// (which the browser would fake by smearing the nearest one).
const root = resolve(__dirname, "..");
const html = readFileSync(resolve(root, "index.html"), "utf8");
const requested = (html.match(/family=Inter:wght@([\d;]+)/) || [])[1]?.split(";").map(Number);

const CLASS_WEIGHTS = {
  "font-thin": 100, "font-extralight": 200, "font-light": 300, "font-normal": 400,
  "font-medium": 500, "font-semibold": 600, "font-bold": 700, "font-extrabold": 800,
  "font-black": 900,
};

function sources(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "data" ? [] : sources(path);
    return /\.(jsx?|css)$/.test(name) && !/\.test\./.test(name) ? [path] : [];
  });
}

function usedWeights() {
  const used = new Set([400]); // the body text, which names no weight at all
  for (const file of sources(resolve(root, "src"))) {
    const text = readFileSync(file, "utf8");
    for (const [cls, weight] of Object.entries(CLASS_WEIGHTS)) {
      if (new RegExp(`\\b${cls}\\b`).test(text)) used.add(weight);
    }
    for (const [, w] of text.matchAll(/font-weight:\s*(\d{3})/g)) used.add(Number(w));
  }
  return [...used].sort();
}

describe("Inter weights", () => {
  it("are requested exactly as the app uses them", () => {
    expect(requested).toEqual(usedWeights());
  });
});
