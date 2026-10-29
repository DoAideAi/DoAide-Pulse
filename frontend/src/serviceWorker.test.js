import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

// public/sw.js run against a stand-in worker scope. v2 served every .js/.css
// cache-first under a name no deploy changed, so the unhashed scripts in
// public/ — the analytics redaction above all — were never updated for a
// returning visitor. Only hashed /assets/ and the font CDN are cache-first now.
const ORIGIN = "https://pulse.doaide.com";
const source = readFileSync(resolve(__dirname, "../public/sw.js"), "utf8");

function worker({ cached = null } = {}) {
  const listeners = {};
  const scope = {
    location: { origin: ORIGIN },
    addEventListener: (type, fn) => (listeners[type] = fn),
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
  };
  const cache = { put: vi.fn(), addAll: vi.fn() };
  const caches = {
    match: vi.fn(async () => cached),
    open: vi.fn(async () => cache),
    keys: vi.fn(async () => []),
  };
  const fetch = vi.fn(async () => ({ clone: () => ({}) }));
  new Function("self", "caches", "fetch", source)(scope, caches, fetch);
  return { listeners, caches, fetch };
}

async function request(path, options) {
  const sw = worker(options);
  let responded = null;
  sw.listeners.fetch({
    request: { method: "GET", url: `${ORIGIN}${path}` },
    respondWith: (promise) => (responded = promise),
  });
  await responded;
  return sw;
}

describe("the service worker", () => {
  it("answers a hashed asset from the cache without the network", async () => {
    const sw = await request("/assets/index-AbC123.js", { cached: { ok: true } });
    expect(sw.fetch).not.toHaveBeenCalled();
  });

  it.each(["/analytics-redact.js", "/theme-init.js", "/embed.js", "/favicon.svg"])(
    "asks the network first for %s, which changes in place",
    async (path) => {
      const sw = await request(path, { cached: { ok: true, stale: true } });
      expect(sw.fetch).toHaveBeenCalledTimes(1);
    },
  );

  it("never touches the API", async () => {
    const sw = worker();
    const respondWith = vi.fn();
    sw.listeners.fetch({
      request: { method: "GET", url: `${ORIGIN}/api/v1/auth/me` },
      respondWith,
    });
    expect(respondWith).not.toHaveBeenCalled();
  });

  it("is a cache name the stale v2 copies are dropped under", () => {
    expect(source).toMatch(/CACHE_NAME = "doaide-pulse-v3"/);
  });
});
