import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { _setEnabled, flush, routePattern, trackAction, trackPageView } from "./activity";

function sent() {
  return fetch.mock.calls.map(([url, init]) => ({ url, init, body: JSON.parse(init.body) }));
}

describe("activity tracker", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    globalThis.fetch = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));
    localStorage.setItem("pulse_token", "tok");
    _setEnabled(true);
  });

  afterEach(() => {
    _setEnabled(false);
    localStorage.clear();
    vi.useRealTimers();
  });

  it("collapses ids and drops the query string", () => {
    expect(routePattern("/content/42?status=review")).toBe("/content/:id");
    expect(routePattern("/content/42/edit#x")).toBe("/content/:id/edit");
    expect(routePattern("/analytics")).toBe("/analytics");
  });

  it("batches events and sends them after a pause, with the bearer token", () => {
    trackPageView("/content/7?q=secret");
    trackAction("POST /content/:id/approve", "/content/7");
    expect(fetch).not.toHaveBeenCalled();

    vi.advanceTimersByTime(5000);

    const [call] = sent();
    expect(call.url).toBe("/api/v1/activity");
    expect(call.init.keepalive).toBe(true);
    expect(call.init.headers.Authorization).toBe("Bearer tok");
    expect(call.body.events).toEqual([
      { kind: "page_view", name: "/content/:id", path: "/content/7" },
      { kind: "action", name: "POST /content/:id/approve", path: "/content/7" },
    ]);
  });

  it("flushes early when the queue fills", () => {
    for (let i = 0; i < 20; i += 1) trackAction(`a${i}`);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(sent()[0].body.events).toHaveLength(20);
  });

  it("records nothing for a signed-out visitor", () => {
    localStorage.removeItem("pulse_token");
    trackPageView("/");
    flush();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("never throws when the network does", () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error("offline")));
    trackAction("x");
    expect(() => flush()).not.toThrow();
  });
});
