import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The landing page's own stylesheet keeps its text at WCAG AA (4.5:1).
 *
 * It does not use the theme tokens that doaideTheme.contrast.test.js checks:
 * it is white at an alpha over near-black, and the subtitles, form labels and
 * sign-in tabs sat at 0.45 and 0.35 — 4.49:1 and 3.2:1 — with placeholders at
 * 0.25 and --text-muted at 3.6:1 on the card surface.
 */
const CSS = readFileSync(resolve(__dirname, "LandingPage.css"), "utf8");

function hex(value) {
  const m = value.trim().match(/^#([0-9a-f]{6})$/i);
  return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16));
}

function variable(name) {
  return CSS.match(new RegExp(`--${name}:\\s*([^;]+);`))[1];
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

function overWhite(alpha, background) {
  return background.map((c) => Math.round(255 * alpha + c * (1 - alpha)));
}

/** Every white-at-an-alpha text colour, with the selector it belongs to. */
function whiteTextColours() {
  const out = [];
  for (const [, selector, body] of CSS.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    for (const [, alpha] of body.matchAll(/(?:^|[;\s])color:\s*rgba\(255,\s*255,\s*255,\s*([\d.]+)\)/g)) {
      out.push([selector.trim().split("\n").pop().trim(), Number(alpha)]);
    }
  }
  return out;
}

const SURFACES = {
  background: hex(variable("bg")),
  "card surface": hex(variable("bg-surface")),
};

describe.each(Object.entries(SURFACES))("on the %s", (_name, surface) => {
  it("every white text colour is readable", () => {
    const colours = whiteTextColours();
    expect(colours.length).toBeGreaterThan(5);
    const failing = colours
      .map(([selector, alpha]) => [selector, alpha, contrast(overWhite(alpha, surface), surface)])
      .filter(([, , ratio]) => ratio < 4.5)
      .map(([selector, alpha, ratio]) => `${selector} @ ${alpha} = ${ratio.toFixed(2)}:1`);
    expect(failing).toEqual([]);
  });

  it("--text-muted is readable", () => {
    expect(contrast(hex(variable("text-muted")), surface)).toBeGreaterThanOrEqual(4.5);
  });
});

// The sign-in inputs drop the browser's focus outline, and all that replaced
// it was the border turning teal at half alpha: about 2:1 against the near-black
// field, under the 3:1 WCAG 1.4.11 asks of a focus indicator. A keyboard user
// tabbing through the form every account signs in with could not see which field
// they were in. The indicator is now a solid ring in --accent-secondary.
describe("the sign-in inputs show where focus is", () => {
  function rule(selector) {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const match = CSS.match(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`));
    return match ? match[1] : "";
  }

  it("draws a solid ring, not a half-transparent border", () => {
    const focus = rule(".landing-input:focus-visible");
    expect(focus).toMatch(/box-shadow:[^;]*var\(--accent-secondary\)/);
    expect(rule(".landing-input:focus")).not.toMatch(/rgba\(13,\s*148,\s*136,\s*0\.5\)/);
  });

  it("the ring stands out from the page at 3:1 or better", () => {
    expect(contrast(hex(variable("accent-secondary")), hex(variable("bg")))).toBeGreaterThanOrEqual(3);
  });
});
