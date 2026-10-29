import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

// The service worker stored whatever came back. Assets are answered from the
// cache first and kept for good, and pulse-web restarts on every deploy: a new
// chunk first requested during that restart got Caddy's 502 stored under its
// URL, and that browser was served the 502 for it from then on — the page that
// chunk carries broken until somebody bumped CACHE_NAME by hand. Pages went the
// same way into the offline fallback. Only a good answer is kept now.

const ORIGIN = "https://pulse.doaide.com";
const source = readFileSync(resolve(__dirname, "../public/sw.js"), "utf8");

function worker(response) {
  const listeners = {};
  const scope = {
    location: { origin: ORIGIN },
    addEventListener: (type, fn) => (listeners[type] = fn),
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
  };
  const cache = { put: vi.fn(), addAll: vi.fn() };
  const caches = {
    match: vi.fn(async () => null),
    open: vi.fn(async () => cache),
    keys: vi.fn(async () => []),
  };
  const fetch = vi.fn(async () => ({ ...response, clone: () => ({ ...response }) }));
  new Function("self", "caches", "fetch", source)(scope, caches, fetch);
  return { listeners, cache };
}

async function request(path, response) {
  const sw = worker(response);
  let responded = null;
  sw.listeners.fetch({
    request: { method: "GET", url: `${ORIGIN}${path}` },
    respondWith: (promise) => (responded = promise),
  });
  const answer = await responded;
  // Let the fire-and-forget cache write settle.
  await new Promise((r) => setTimeout(r, 0));
  return { ...sw, answer };
}

describe("the service worker keeps only good answers", () => {
  it.each([502, 503, 404])("does not keep an asset that answered %i", async (status) => {
    const sw = await request("/assets/Editor-Xy12.js", { ok: false, status, type: "basic" });
    expect(sw.answer.status).toBe(status);
    expect(sw.cache.put).not.toHaveBeenCalled();
  });

  it("does not keep a page that answered with an error", async () => {
    const sw = await request("/calendar", { ok: false, status: 500, type: "basic" });
    expect(sw.cache.put).not.toHaveBeenCalled();
  });

  it("does not keep an opaque answer it cannot inspect", async () => {
    const sw = await request("/assets/x.js", { ok: false, status: 0, type: "opaque" });
    expect(sw.cache.put).not.toHaveBeenCalled();
  });

  it("still keeps a good asset", async () => {
    const sw = await request("/assets/Editor-Xy12.js", { ok: true, status: 200, type: "basic" });
    expect(sw.cache.put).toHaveBeenCalledTimes(1);
  });

  it("still keeps a good page for offline use", async () => {
    const sw = await request("/calendar", { ok: true, status: 200, type: "basic" });
    expect(sw.cache.put).toHaveBeenCalledTimes(1);
  });

  it("names a new cache, so browsers drop what the old worker stored", () => {
    expect(source).not.toMatch(/CACHE_NAME = "doaide-pulse-v3"/);
  });
});
