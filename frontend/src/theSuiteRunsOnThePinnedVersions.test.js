import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The frontend twin of backend/tests/test_the_suite_runs_on_the_pinned_versions.py.
//
// package.json pins exact versions and the deploy installs them with `npm ci`.
// A local node_modules is whatever was installed last, and nobody reinstalls
// when a pin moves: on 2026-10-29 the suite was green on react-router-dom
// 7.18.2, @testing-library/react 16.3.2, postcss and autoprefixer a release or
// more behind what the box was building with. So this compares what is
// installed here with what is pinned, and the lockfile with both.
const root = resolve(__dirname, "..");
const pkg = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
const lock = JSON.parse(readFileSync(resolve(root, "package-lock.json"), "utf8"));
const pins = { ...pkg.dependencies, ...pkg.devDependencies };

describe("dependencies", () => {
  it("pins exact versions", () => {
    const ranged = Object.entries(pins).filter(([, v]) => !/^\d+\.\d+\.\d+$/.test(v));
    expect(ranged).toEqual([]);
  });

  it("has a lockfile that agrees with package.json", () => {
    const drift = Object.entries(pins)
      .map(([name, v]) => [name, v, lock.packages[`node_modules/${name}`]?.version])
      .filter(([, v, locked]) => v !== locked);
    expect(drift).toEqual([]);
  });

  it("runs on the pinned versions — run `npm ci` when this fails", () => {
    const drift = Object.entries(pins)
      .map(([name, v]) => {
        const file = resolve(root, "node_modules", name, "package.json");
        const installed = existsSync(file) ? JSON.parse(readFileSync(file, "utf8")).version : null;
        return [name, v, installed];
      })
      .filter(([, v, installed]) => v !== installed);
    expect(drift).toEqual([]);
  });
});
