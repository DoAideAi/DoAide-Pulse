import { describe, expect, it, vi } from "vitest";
import registerServiceWorker from "./registerServiceWorker";

function fakeWindow() {
  const listeners = {};
  return {
    addEventListener: (name, fn) => (listeners[name] = fn),
    fire: (name) => listeners[name]?.(),
  };
}

describe("registerServiceWorker", () => {
  it("registers /sw.js after load", async () => {
    const register = vi.fn(() => Promise.resolve());
    const win = fakeWindow();

    expect(registerServiceWorker({ serviceWorker: { register } }, win)).toBe(true);
    expect(register).not.toHaveBeenCalled();
    win.fire("load");
    expect(register).toHaveBeenCalledWith("/sw.js");
  });

  it("swallows a failed registration", async () => {
    const register = vi.fn(() => Promise.reject(new Error("insecure")));
    const win = fakeWindow();
    registerServiceWorker({ serviceWorker: { register } }, win);

    win.fire("load");
    await Promise.resolve();
    expect(register).toHaveBeenCalled();
  });

  it("does nothing where service workers are unsupported", () => {
    expect(registerServiceWorker({}, fakeWindow())).toBe(false);
  });
});
