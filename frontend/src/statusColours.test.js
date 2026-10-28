// Error text uses the theme's `bad` token, never a raw Tailwind red.
//
// `--c-bad` is set once for light mode and once for dark, each tuned to clear
// WCAG AA on that theme's surfaces. A raw `text-rose-600` is one shade for
// both: fine on white, about 3.6:1 on the dark surface — under the 4.5:1 that
// the 11–12px error lines it was used for need. Templates carried four.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = resolve(__dirname);

function sources(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(jsx|js)$/.test(name) && !/\.test\./.test(name) ? [path] : [];
  });
}

describe("status colours", () => {
  it("come from the theme tokens, so dark mode stays legible", () => {
    const raw = sources(ROOT).flatMap((path) =>
      [...readFileSync(path, "utf8").matchAll(/\btext-(red|rose)-\d{2,3}\b/g)].map(
        (m) => `${relative(ROOT, path)}: ${m[0]}`,
      ),
    );
    expect(raw).toEqual([]);
  });
});
