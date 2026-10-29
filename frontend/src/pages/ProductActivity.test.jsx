import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProductActivity from "./ProductActivity";
import { api } from "../lib/api";
import { AUTO_REFRESH_MS } from "../lib/productActivity";
import { ROUTER_FUTURE } from "../lib/routerFuture";

vi.mock("../lib/api", () => ({
  api: { productActivity: vi.fn() },
}));

function umami(overrides = {}) {
  return {
    status: "ok",
    error: null,
    website_id: "w",
    pageviews: 1200,
    visitors: 300,
    visits: 400,
    bounces: 100,
    totaltime: 24000,
    active_now: 0,
    top_pages: [{ name: "/", count: 800 }],
    ...overrides,
  };
}

function product(key, name, overrides = {}) {
  return {
    key,
    name,
    domain: `${key}.doaide.com`,
    url: `https://${key}.doaide.com`,
    umami: umami(),
    signups: 0,
    logins: 0,
    key_actions: [],
    reported_events: 0,
    ...overrides,
  };
}

function payload(overrides = {}) {
  return {
    days: 7,
    generated_at: new Date().toISOString(),
    umami_configured: true,
    umami_error: null,
    totals: { pageviews: 2400, visitors: 600, active_now: 3, signups: 4, logins: 9 },
    products: [
      product("gst", "GST", {
        signups: 4,
        key_actions: [{ label: "GST calculations", events: ["gst_calculation"], count: 57 }],
      }),
      product("autoapply", "AutoApply", { umami: umami({ active_now: 3 }) }),
      product("prospect", "Prospect", { umami: { status: "not_found", top_pages: [] } }),
    ],
    recent: [
      {
        product: "gst",
        product_name: "GST",
        kind: "signup",
        actor: "s***@example.com",
        occurred_at: new Date().toISOString(),
      },
    ],
    ...overrides,
  };
}

function draw() {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <ProductActivity />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  api.productActivity.mockReset();
  api.productActivity.mockResolvedValue(payload());
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ProductActivity", () => {
  it("shows the totals and one card per product", async () => {
    draw();
    expect(await screen.findByRole("article", { name: "GST" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "AutoApply" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Prospect" })).toBeInTheDocument();
    expect(screen.getByText("2,400")).toBeInTheDocument();
    expect(api.productActivity).toHaveBeenCalledWith(7);
  });

  it("puts the product with live visitors first", async () => {
    draw();
    await screen.findByRole("article", { name: "GST" });
    const names = within(screen.getByRole("region", { name: "Products" }))
      .getAllByRole("article")
      .map((el) => el.getAttribute("aria-label"));
    expect(names).toEqual(["AutoApply", "GST", "Prospect"]);
  });

  it("shows key actions, traffic figures and top pages on a card", async () => {
    draw();
    const gst = await screen.findByRole("article", { name: "GST" });
    expect(within(gst).getByText("GST calculations")).toBeInTheDocument();
    expect(within(gst).getByText("57")).toBeInTheDocument();
    expect(within(gst).getByText("25%")).toBeInTheDocument(); // bounce 100/400
    expect(within(gst).getByText("1m 00s")).toBeInTheDocument(); // 24000s / 400
    expect(within(gst).getByText("/")).toBeInTheDocument();
  });

  it("says why a product has no traffic numbers", async () => {
    draw();
    const prospect = await screen.findByRole("article", { name: "Prospect" });
    expect(within(prospect).getByText(/No Umami site found/)).toBeInTheDocument();
  });

  it("lists recent signups with the masked actor", async () => {
    draw();
    const feed = await screen.findByRole("region", { name: "Recent signups and logins" });
    expect(within(feed).getByText("s***@example.com")).toBeInTheDocument();
    expect(within(feed).getByText("Signup")).toBeInTheDocument();
  });

  it("explains how to report events when the feed is empty", async () => {
    api.productActivity.mockResolvedValue(payload({ recent: [] }));
    draw();
    expect(await screen.findByText(/Nothing reported yet/)).toBeInTheDocument();
  });

  it("surfaces an unconfigured Umami without hiding the page", async () => {
    api.productActivity.mockResolvedValue(
      payload({ umami_configured: false, umami_error: "Umami is not configured." }),
    );
    draw();
    // The loading announcement is a status too; this waits for the one meant.
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Umami is not configured."));
    expect(screen.getByRole("article", { name: "GST" })).toBeInTheDocument();
  });

  it("refresh skips the server cache", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByRole("article", { name: "GST" });
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(api.productActivity).toHaveBeenLastCalledWith(7, { refresh: true });
  });

  it("switches the window", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByRole("article", { name: "GST" });
    await user.click(screen.getByRole("button", { name: "30d" }));
    expect(api.productActivity).toHaveBeenLastCalledWith(30);
  });

  it("shows an error with a retry", async () => {
    api.productActivity.mockRejectedValueOnce(new Error("Forbidden"));
    draw();
    expect(await screen.findByRole("alert")).toHaveTextContent("Forbidden");
  });

  it("re-asks every minute, and stops when auto-refresh is off", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    draw();
    await screen.findByRole("article", { name: "GST" });
    expect(api.productActivity).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(AUTO_REFRESH_MS);
    });
    expect(api.productActivity).toHaveBeenCalledTimes(2);

    await user.click(screen.getByRole("checkbox", { name: "Auto-refresh" }));
    await act(async () => {
      vi.advanceTimersByTime(AUTO_REFRESH_MS * 2);
    });
    expect(api.productActivity).toHaveBeenCalledTimes(2);
  });
});
