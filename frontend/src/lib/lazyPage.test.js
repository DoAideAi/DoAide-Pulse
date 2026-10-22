import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadWithReload, RELOAD_FLAG } from "./lazyPage";

const store = new Map();

beforeEach(() => {
  store.clear();
  Object.defineProperty(window, "sessionStorage", {
    value: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => void store.set(k, String(v)),
      removeItem: (k) => void store.delete(k),
    },
    configurable: true,
  });
});

describe("loadWithReload", () => {
  it("passes a loaded module through and clears a stale flag", async () => {
    store.set(RELOAD_FLAG, "1");
    const module = { default: () => null };

    await expect(loadWithReload(() => Promise.resolve(module))).resolves.toBe(module);
    expect(store.has(RELOAD_FLAG)).toBe(false);
  });

  it("reloads once when a chunk from before a deploy is gone", async () => {
    const reload = vi.fn();
    const pending = loadWithReload(() => Promise.reject(new Error("404")), { reload });

    await new Promise((r) => setTimeout(r, 0));
    expect(reload).toHaveBeenCalledTimes(1);
    expect(store.get(RELOAD_FLAG)).toBe("1");
    // Left pending, so no fallback flashes while the page goes away.
    let settled = false;
    pending.then(() => (settled = true), () => (settled = true));
    await new Promise((r) => setTimeout(r, 0));
    expect(settled).toBe(false);
  });

  it("lets a second failure reach the error boundary instead of looping", async () => {
    store.set(RELOAD_FLAG, "1");
    const reload = vi.fn();

    await expect(
      loadWithReload(() => Promise.reject(new Error("offline")), { reload }),
    ).rejects.toThrow("offline");
    expect(reload).not.toHaveBeenCalled();
  });

  it("rethrows when there is no session storage to remember the attempt", async () => {
    Object.defineProperty(window, "sessionStorage", {
      get() {
        throw new Error("blocked");
      },
      configurable: true,
    });
    const reload = vi.fn();

    await expect(
      loadWithReload(() => Promise.reject(new Error("gone")), { reload }),
    ).rejects.toThrow("gone");
    expect(reload).not.toHaveBeenCalled();
  });
});
