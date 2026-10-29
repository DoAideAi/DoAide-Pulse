import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ErrorBoundary from "../components/ErrorBoundary";
import { whileCaught } from "../test/caught";
import {
  _setEnabled,
  componentNames,
  reportRenderError,
  reportUncaughtErrors,
} from "./clientErrors";

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

  it("says which build crashed, so a deploy's crash is told from a stale tab's", () => {
    // The server logs release=- for a report without one, and every report was
    // without one: after a deploy, nothing said whether a crash came from the
    // new code or from a tab still running the old bundle.
    reportRenderError(new Error("x"), { componentStack: "" }, "s");
    expect(sentBodies()[0].release).toBe("test-release");
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

describe("an error outside rendering", () => {
  // An error boundary only sees render throws. A TypeError in a click handler,
  // or a promise nobody awaited, went to the console of the browser it
  // happened in and nowhere else — the server never heard of the commonest
  // kind of front-end failure.
  let stop;
  beforeEach(() => {
    stop = reportUncaughtErrors();
  });
  afterEach(() => stop());

  it("is reported when a handler throws", () => {
    const error = new TypeError("Cannot read properties of null (reading 'id')");
    window.dispatchEvent(new ErrorEvent("error", { error, message: error.message }));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [body] = sentBodies();
    expect(body.section).toBe("window:error");
    expect(body.name).toBe("TypeError");
    expect(body.message).toContain("reading 'id'");
  });

  it("is reported when a promise is rejected and nobody handles it", () => {
    const event = new Event("unhandledrejection");
    event.reason = new RangeError("Invalid time value");
    window.dispatchEvent(event);

    const [body] = sentBodies();
    expect(body.section).toBe("window:unhandledrejection");
    expect(body.name).toBe("RangeError");
  });

  it("leaves out an API refusal, which the page already showed", () => {
    // Every request() failure carries the HTTP status (0 for no answer); the
    // server logged its own side, and the toast told the user.
    const event = new Event("unhandledrejection");
    event.reason = Object.assign(new Error("Too many requests"), { status: 429 });
    window.dispatchEvent(event);

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("leaves out a cross-origin script's opaque error and the ResizeObserver notice", () => {
    window.dispatchEvent(new ErrorEvent("error", { message: "Script error." }));
    window.dispatchEvent(
      new ErrorEvent("error", { message: "ResizeObserver loop completed with undelivered notifications." }),
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports an error event that carries only a message", () => {
    window.dispatchEvent(new ErrorEvent("error", { message: "Something odd" }));
    expect(sentBodies()[0].message).toBe("Something odd");
  });

  it("reports a rejection with something other than an Error", () => {
    const event = new Event("unhandledrejection");
    event.reason = "plain string";
    window.dispatchEvent(event);
    expect(sentBodies()[0].message).toBe("plain string");
  });

  it("stops listening when asked", () => {
    stop();
    window.dispatchEvent(new ErrorEvent("error", { error: new Error("late"), message: "late" }));
    expect(fetchMock).not.toHaveBeenCalled();
    stop = () => {};
  });
});
