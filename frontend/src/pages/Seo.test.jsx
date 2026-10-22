import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Seo from "./Seo";
import { api } from "../lib/api";
import { ROUTER_FUTURE } from "../lib/routerFuture";

vi.mock("../lib/api", () => ({
  api: {
    seoHealth: vi.fn(),
    seoHealthHistory: vi.fn(),
    seoSitemaps: vi.fn(),
    seoSitemapRuns: vi.fn(),
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

function draw(path = "/seo?tab=sitemaps") {
  return render(
    <MemoryRouter initialEntries={[path]} future={ROUTER_FUTURE}>
      <Seo />
    </MemoryRouter>,
  );
}

describe("SEO page — sitemaps", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.seoSitemapRuns.mockResolvedValue({ runs: [] });
    api.seoHealthHistory.mockResolvedValue({ days: 90, points: [] });
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

  it("shows the submission run log with its problems", async () => {
    api.seoSitemaps.mockResolvedValue({ gsc_configured: true, gsc_account: null, sites: [site("gst")] });
    api.seoSitemapRuns.mockResolvedValue({
      runs: [
        {
          id: 2,
          trigger: "manual",
          sites_checked: 14,
          sites_submitted: 13,
          problems: [{ site_key: "comply", error: "sitemap answered 404" }],
          ran_at: "2026-10-22T09:00:00Z",
        },
        {
          id: 1,
          trigger: "scheduled",
          sites_checked: 14,
          sites_submitted: 14,
          problems: [],
          ran_at: "2026-10-20T02:30:00Z",
        },
      ],
    });
    draw();

    const history = await screen.findByRole("region", { name: "Submission history" });
    const rows = within(history).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("manual");
    expect(rows[0]).toHaveTextContent("comply");
    expect(rows[0]).toHaveTextContent("sitemap answered 404");
    expect(rows[1]).toHaveTextContent("scheduled");
    expect(within(rows[1]).getByText("none")).toBeInTheDocument();
  });
});

describe("SEO page — health", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.seoSitemapRuns.mockResolvedValue({ runs: [] });
    api.seoHealthHistory.mockResolvedValue({ days: 90, points: [] });
  });

  function health(overrides = {}) {
    return {
      generated_at: "2026-10-22T10:00:00Z",
      totals: {
        sites: 14,
        sitemaps_submitted: 12,
        sitemap_problems: 1,
        urls_in_sitemaps: 420,
        indexed_pages: 300,
        posts_published_30d: 3,
        posts_scheduled: 2,
        meta_issues: 7,
      },
      sites: [{ ...site("tax"), recent_posts: 2, scheduled_posts: 1, meta_issues: 7 }],
      recent_posts: [
        {
          id: 5,
          title: "File ITR online",
          slug: "file-itr-online",
          status: "published",
          focus_keyword: "itr",
          published_at: "2026-10-20T10:00:00Z",
          scheduled_for: null,
          created_at: "2026-10-19T10:00:00Z",
          site_key: "tax",
        },
      ],
      calendar: [
        { date: "2026-10-22", posts: [] },
        {
          date: "2026-10-23",
          posts: [{ id: 7, title: "GST due dates", status: "approved", when: "2026-10-23T08:00:00Z" }],
        },
      ],
      ...overrides,
    };
  }

  it("opens on health by default and shows the totals, sites, calendar and posts", async () => {
    api.seoHealth.mockResolvedValue(health());
    draw("/seo");

    expect(await screen.findByText("12/14")).toBeInTheDocument();
    expect(screen.getByText("1 with problems")).toBeInTheDocument();
    expect(api.seoHealth).toHaveBeenCalledWith(expect.any(String));

    const sites = screen.getByRole("region", { name: "Sites" });
    expect(within(sites).getByText("tax.doaide.com")).toBeInTheDocument();

    const cal = screen.getByRole("region", { name: "Content calendar" });
    expect(within(cal).getByRole("link", { name: "GST due dates" })).toHaveAttribute("href", "/content/7");

    const recent = screen.getByRole("region", { name: "Recent SEO posts" });
    expect(within(recent).getByRole("link", { name: "File ITR online" })).toBeInTheDocument();
  });

  it("draws the health-over-time charts once there are two snapshots", async () => {
    api.seoHealth.mockResolvedValue(health());
    const day = (date, urls) => ({
      date,
      sites: 14,
      sitemaps_submitted: 12,
      sitemap_problems: 1,
      urls_in_sitemaps: urls,
      indexed_pages: 300,
      meta_issues: 7,
    });
    api.seoHealthHistory.mockResolvedValue({
      days: 90,
      points: [day("2026-10-21", 410), day("2026-10-22", 420)],
    });
    draw("/seo");

    const section = await screen.findByRole("region", { name: "Health over time" });
    expect(within(section).getByText("Pages in search")).toBeInTheDocument();
    expect(within(section).getByText("Problems")).toBeInTheDocument();
    expect(api.seoHealthHistory).toHaveBeenCalledWith(90);
  });

  it("says so instead of drawing a chart from one snapshot", async () => {
    api.seoHealth.mockResolvedValue(health());
    draw("/seo");

    const section = await screen.findByRole("region", { name: "Health over time" });
    expect(
      within(section).getByText(/chart starts drawing after two days of data/),
    ).toBeInTheDocument();
  });

  it("switches tabs and keeps the choice in the URL", async () => {
    api.seoHealth.mockResolvedValue(health({ recent_posts: [] }));
    api.seoSitemaps.mockResolvedValue({ gsc_configured: true, gsc_account: null, sites: [site("gst")] });
    draw("/seo");

    expect(await screen.findByText(/Nothing published yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Sitemaps" }));
    expect(await screen.findByRole("tab", { name: "Sitemaps" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("gst.doaide.com")).toBeInTheDocument();
  });
});
