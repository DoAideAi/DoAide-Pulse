import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Seo from "./Seo";
import { api } from "../lib/api";
import { ROUTER_FUTURE } from "../lib/routerFuture";

vi.mock("../lib/api", () => ({
  api: {
    seoSitemaps: vi.fn(),
    submitSitemaps: vi.fn(),
  },
}));

function site(key, overrides = {}) {
  return {
    key,
    name: key.toUpperCase(),
    domain: `${key}.doaide.com`,
    url: `https://${key}.doaide.com/`,
    sitemap_url: `https://${key}.doaide.com/sitemap.xml`,
    checked: true,
    url_count: 12,
    fetch_error: null,
    submit_status: "submitted",
    submit_error: null,
    gsc_submitted: 12,
    gsc_indexed: 9,
    gsc_errors: 0,
    gsc_warnings: 0,
    gsc_last_downloaded: null,
    submitted_at: "2026-10-20T00:00:00Z",
    checked_at: "2026-10-20T00:00:00Z",
    ...overrides,
  };
}

function draw(path = "/seo") {
  return render(
    <MemoryRouter initialEntries={[path]} future={ROUTER_FUTURE}>
      <Seo />
    </MemoryRouter>,
  );
}

describe("SEO page — sitemaps", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists every site with its counts and puts problems first", async () => {
    api.seoSitemaps.mockResolvedValue({
      gsc_configured: true,
      gsc_account: "pulse@doaide.iam.gserviceaccount.com",
      sites: [site("gst"), site("comply", { fetch_error: "https://comply.doaide.com/sitemap.xml answered 404", url_count: null })],
    });
    draw();

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("comply.doaide.com");
    expect(rows[0]).toHaveTextContent("Sitemap unreachable");
    expect(rows[1]).toHaveTextContent("gst.doaide.com");
    expect(rows[1]).toHaveTextContent("9");
    expect(screen.getByText(/pulse@doaide.iam.gserviceaccount.com/)).toBeInTheDocument();
  });

  it("says plainly when nothing can be submitted", async () => {
    api.seoSitemaps.mockResolvedValue({
      gsc_configured: false,
      gsc_account: null,
      sites: [site("gst", { submit_status: "unconfigured" })],
    });
    draw();
    expect(await screen.findByRole("status")).toHaveTextContent("No Search Console service account");
  });

  it("submits one site and shows the answer", async () => {
    api.seoSitemaps.mockResolvedValue({
      gsc_configured: true,
      gsc_account: null,
      sites: [site("desk", { checked: false, submit_status: "pending", checked_at: null })],
    });
    api.submitSitemaps.mockResolvedValue({
      gsc_configured: true,
      gsc_account: null,
      sites: [site("desk")],
    });
    draw();

    await userEvent.click(await screen.findByRole("button", { name: "Submit desk.doaide.com" }));
    expect(api.submitSitemaps).toHaveBeenCalledWith("desk");
    expect(await screen.findByText("Submitted")).toBeInTheDocument();
  });

  it("shows a failed submission instead of swallowing it", async () => {
    api.seoSitemaps.mockResolvedValue({ gsc_configured: true, gsc_account: null, sites: [site("gst")] });
    api.submitSitemaps.mockRejectedValue(new Error("Search Console answered 500"));
    draw();

    await userEvent.click(await screen.findByRole("button", { name: "Submit all" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Search Console answered 500");
  });
});
