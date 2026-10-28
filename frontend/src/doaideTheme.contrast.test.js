import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Every text token clears WCAG AA (4.5:1) on both surfaces, in both themes.
 *
 * ink-400 did not: 2.4:1 in light mode and 3.6:1 in dark, while being the
 * colour of every form label, eyebrow and placeholder — 10px text, which is
 * exactly the size AA's 4.5:1 is for.
 */
const CSS = readFileSync(resolve(__dirname, "doaide-theme.css"), "utf8");

function tokens(selector) {
  const block = CSS.match(new RegExp(`${selector}\\s*\\{([\\s\\S]*?)\\n\\}`))[1];
  return Object.fromEntries(
    [...block.matchAll(/--c-([a-z0-9-]+):\s*(\d+)\s+(\d+)\s+(\d+);/g)].map((m) => [
      m[1],
      [Number(m[2]), Number(m[3]), Number(m[4])],
    ]),
  );
}

function luminance(rgb) {
  const [r, g, b] = rgb.map((c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe.each([
  ["light", ":root"],
  ["dark", "\\.dark"],
])("%s theme", (_name, selector) => {
  const t = tokens(selector);
  it.each(["ink-900", "ink-700", "ink-500", "ink-400"])("%s is readable on canvas and paper", (ink) => {
    expect(contrast(t[ink], t.canvas)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t[ink], t.paper)).toBeGreaterThanOrEqual(4.5);
  });
});
