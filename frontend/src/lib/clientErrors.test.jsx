import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ErrorBoundary from "../components/ErrorBoundary";
import { whileCaught } from "../test/caught";
import { _setEnabled, componentNames, reportRenderError } from "./clientErrors";

// A boundary that tripped used to show its panel and nothing else: the stack
// went to the one browser's console, and the server never heard of it.

function Boom({ message = "Cannot read properties of undefined (reading 'length')" }) {
  throw new TypeError(message);
}

let fetchMock;

beforeEach(() => {
  _setEnabled(true);
  fetchMock = vi.fn(() => Promise.resolve({ ok: true }));
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
});

afterEach(() => {
  _setEnabled(false);
  vi.unstubAllGlobals();
});

function sentBodies() {
  return fetchMock.mock.calls.map(([, init]) => JSON.parse(init.body));
}

describe("a caught render crash", () => {
  it("is reported to the server with what to act on", async () => {
    await whileCaught(() =>
      render(
        <ErrorBoundary section="dashboard:review-queue">
          <Boom />
        </ErrorBoundary>,
      ),
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/client-errors");
    expect(init.method).toBe("POST");
    expect(init.keepalive).toBe(true);
    const [body] = sentBodies();
    expect(body.section).toBe("dashboard:review-queue");
    expect(body.name).toBe("TypeError");
    expect(body.message).toContain("reading 'length'");
    expect(body.components).toContain("Boom");
  });

  it("names the account when there is one", () => {
    localStorage.setItem("pulse_token", "tok");
    reportRenderError(new Error("x"), { componentStack: "" }, "s");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer tok");
  });

  it("sends the route pattern, never the address with its secret in it", () => {
    window.history.pushState({}, "", "/preview/abcDEF0123456789abcDEF0123456789abcDEF01234");
    reportRenderError(new Error("x"), {}, "preview");
    expect(sentBodies()[0].route).toBe("/preview/:token");
    window.history.pushState({}, "", "/");
  });

  it("says the same thing once, and at most five things a page", () => {
    for (let i = 0; i < 3; i++) reportRenderError(new Error("same"), {}, "row");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 10; i++) reportRenderError(new Error(`row ${i}`), {}, "row");
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it("never becomes a second crash", () => {
    vi.stubGlobal("fetch", () => {
      throw new Error("no network stack");
    });
    expect(() => reportRenderError(new Error("x"), {}, "s")).not.toThrow();
  });
});

describe("componentNames", () => {
  it("reads Chrome, Firefox and React stacks", () => {
    const chrome = "\n    at Boom (http://x/assets/a.js:1:2)\n    at ErrorBoundary (http://x/b.js:3:4)";
    const firefox = "Boom@http://x/assets/a.js:1:2\nErrorBoundary@http://x/b.js:3:4";
    const react = "\n    in Boom\n    in ErrorBoundary";
    for (const stack of [chrome, firefox, react]) {
      expect(componentNames(stack)).toEqual(["Boom", "ErrorBoundary"]);
    }
  });
});
