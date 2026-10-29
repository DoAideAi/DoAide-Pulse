/**
 * The route table, and where the error boundaries sit in it.
 *
 * The boundaries are the reason this file exists: their placement is the part
 * that can silently regress — moving one outside `Shell`, or dropping it from a
 * route — without any single component's own tests noticing. What is asserted
 * here is the user-visible consequence of the placement: a page that throws
 * still leaves a way out of it.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { ROUTER_FUTURE } from "./lib/routerFuture";
import { whileCaught } from "./test/caught";

vi.mock("./hooks/useAuth", () => ({
  useAuth: vi.fn(),
}));

vi.mock("./lib/api", () => ({
  api: {
    reviewQueue: vi.fn(() => Promise.resolve([])),
    publicationQueue: vi.fn(() => Promise.resolve([])),
    queueCounts: vi.fn(() => Promise.resolve({ review: 0, failed: 0 })),
  },
  getToken: vi.fn(() => "token"),
  setToken: vi.fn(),
}));

// Stand-ins for the two pages this file navigates between. The real ones would
// drag their own fetches in and make a boundary test into a page test.
vi.mock("./pages/Dashboard", () => ({
  default: () => {
    throw new Error("dashboard exploded");
  },
}));

vi.mock("./pages/LandingPage", async () => {
  const { useLocation } = await import("react-router-dom");
  return {
    default: function Landing() {
      const from = useLocation().state?.from;
      return <p>landing{from ? ` (back to ${from})` : ""}</p>;
    },
  };
});

vi.mock("./pages/Projects", () => ({
  default: () => <p>the projects page</p>,
}));

vi.mock("./pages/Login", () => ({
  default: () => {
    throw new Error("login exploded");
  },
}));

import { useAuth } from "./hooks/useAuth";

function signedIn(overrides = {}) {
  useAuth.mockReturnValue({
    user: { email: "writer@example.com" },
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
    ...overrides,
  });
}

/**
 * Mount the app at `path` and let the Shell's two queue counts land.
 *
 * Without the flush their `setState` arrives after the test body has finished,
 * outside `act`, and React says so on the console — which the guard in
 * `test/setup.js` correctly treats as a failure.
 */
async function draw(path) {
  const result = render(
    <MemoryRouter future={ROUTER_FUTURE} initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
  await settle();
  return result;
}

/**
 * Let every promise already in flight resolve inside `act`.
 *
 * A macrotask rather than a bare microtask flush: the pages are lazy chunks,
 * and their dynamic imports settle a few ticks after the render that asked.
 */
function settle() {
  return act(() => new Promise((resolve) => setTimeout(resolve, 0)));
}

/** Follow a nav link, then let the refreshed queue counts land. */
async function clickNav(name) {
  fireEvent.click(screen.getByRole("link", { name }));
  await settle();
}

beforeEach(() => {
  signedIn();
});

describe("the gate", () => {
  it("holds a protected route until the session resolves", async () => {
    signedIn({ user: null, loading: true });

    await draw("/dashboard");

    expect(screen.getByText("Loading")).toBeInTheDocument();
  });

  it("sends a signed-out visitor to the landing page", async () => {
    signedIn({ user: null, loading: false });

    await draw("/dashboard");

    expect(screen.getByText(/^landing/)).toBeInTheDocument();
  });

  // A link from an email — the digest's "turn it off" goes to /settings#digest
  // — used to land on the dashboard once the visitor had signed in, with the
  // place they were sent to forgotten at the gate.
  it("remembers where the signed-out visitor was going", async () => {
    signedIn({ user: null, loading: false });

    await draw("/settings?tab=x#digest");

    expect(screen.getByText("landing (back to /settings?tab=x#digest)")).toBeInTheDocument();
  });
});

describe("a page that throws", () => {
  it("leaves the navigation standing, so there is a way out of it", async () => {
    await whileCaught(() => draw("/dashboard"));

    expect(screen.getByRole("alert")).toHaveTextContent(
      /this page stopped working/i,
    );
    // The chrome outside the boundary survived: wordmark, destinations, account.
    expect(screen.getByRole("link", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByText("writer@example.com")).toBeInTheDocument();
  });

  it("speaks about the page, not about a section of it", async () => {
    await whileCaught(() => draw("/dashboard"));

    const alert = screen.getByRole("alert");
    // The whole page threw: "the rest of the page is unaffected" was untrue.
    expect(alert).not.toHaveTextContent(/rest of the page/i);
    expect(alert).toHaveTextContent(/failed to render/i);
  });

  it("keeps the error's message, so the fallback is worth screenshotting", async () => {
    await whileCaught(() => draw("/dashboard"));

    expect(screen.getByText("dashboard exploded")).toBeInTheDocument();
  });

  it("recovers as soon as the user navigates away from it", async () => {
    await whileCaught(() => draw("/dashboard"));

    await clickNav("Projects");

    expect(screen.getByText("the projects page")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("an unshelled route that throws", () => {
  it("centres its own fallback, having no chrome to sit under", async () => {
    signedIn({ user: null, loading: false });

    await whileCaught(() => draw("/login"));

    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
    // Its own framing, not the Shell's: no navigation on this page at all.
    expect(screen.queryByRole("link", { name: "Projects" })).not.toBeInTheDocument();
    expect(alert.parentElement).toHaveClass("max-w-md");
    // With no chrome at all, a "section" wording and a "rest of the page" were
    // both wrong.
    expect(alert).toHaveTextContent(/this page could not load/i);
    expect(alert).not.toHaveTextContent(/rest of the page/i);
  });
});

describe("the route table", () => {
  it("says an unknown path is not there rather than redirecting", async () => {
    await draw("/no-such-page");

    expect(
      await screen.findByRole("heading", { name: /couldn.t find that page/i }),
    ).toBeInTheDocument();
    // The address is quoted so a typo is visible.
    expect(screen.getByText("/no-such-page")).toBeInTheDocument();
    // Signed in, so the way on is the dashboard — offered, not forced.
    expect(screen.getByRole("link", { name: "Go to your dashboard" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(screen.queryByText("dashboard exploded")).not.toBeInTheDocument();
  });

  it("renders a protected page inside the Shell when it does not throw", async () => {
    await draw("/projects");

    expect(screen.getByText("the projects page")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  });
});
