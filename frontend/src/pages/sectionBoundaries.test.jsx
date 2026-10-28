/**
 * Where the section boundaries sit, checked through the pages that carry them.
 *
 * `ErrorBoundary.test.jsx` proves the mechanism; this proves the placement,
 * which is the half that regresses silently. A boundary moved one level up, or
 * a new panel added without one, breaks nothing any single component's tests
 * would notice — the page simply goes back to blanking itself the next time a
 * response arrives in a shape the API never promised.
 *
 * Two of these three provoke the failure with data rather than a mocked
 * component, because that is the failure being defended against: a field that
 * stopped being sent, reached during render.
 */
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Analytics from "./Analytics";
import ContentEditor from "./ContentEditor";
import Dashboard from "./Dashboard";
import { api } from "../lib/api";
import { ROUTER_FUTURE } from "../lib/routerFuture";
import { whileCaught } from "../test/caught";

vi.mock("../lib/api", () => ({
  api: {
    analytics: vi.fn(),
    engagementTrend: vi.fn(),
    velocity: vi.fn(),
    alerts: vi.fn(),
    // The Analytics page grew pipeline and activity panels; an unmocked call
    // threw "api.pipeline is not a function" and took the whole page down.
    pipeline: vi.fn(),
    // And the M15 panels: feature usage, the content funnel, autopilot.
    featureUsage: vi.fn(),
    contentFunnel: vi.fn(),
    autopilotEffectiveness: vi.fn(),
    activitySummary: vi.fn(),
    subscriberGrowth: vi.fn(),
    dashboard: vi.fn(),
    readTime: vi.fn(),
    reviewQueue: vi.fn(),
    listContent: vi.fn(),
    bulkApprove: vi.fn(),
    approveContent: vi.fn(),
    getContent: vi.fn(),
    platforms: vi.fn(),
    checkLinks: vi.fn(),
    socialCards: vi.fn(),
    listPreviewLinks: vi.fn(),
    listRevisions: vi.fn(),
    listLanguages: vi.fn(),
    listTranslations: vi.fn(),
  },
}));

vi.mock("../components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

// The one component stand-in in this file: read-time is defensive enough that
// there is no field to withhold, so the throw has to be planted.
vi.mock("../components/ReadTimePanel", () => ({
  default: () => {
    throw new Error("read-time exploded");
  },
}));

const FALLBACK = "This panel could not be drawn";

/** Mount `ui` and let the page's own requests settle. */
async function draw(ui) {
  const result = render(
    <MemoryRouter future={ROUTER_FUTURE} initialEntries={["/content/3"]}>
      <Routes>
        <Route path="/content/:contentId" element={ui} />
        <Route path="*" element={ui} />
      </Routes>
    </MemoryRouter>,
  );
  await act(async () => {});
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  api.reviewQueue.mockResolvedValue([]);
  api.listContent.mockResolvedValue([]);
  // The dashboard's setup checklist asks which platforms are connected.
  api.platforms.mockResolvedValue([]);
});

describe("the analytics page", () => {
  function overview() {
    return {
      totals: {
        content_count: 12,
        published_count: 8,
        publication_count: 14,
        views: 4200,
        reads: 900,
        clicks: 210,
        engagement: 340,
        reads_reported: 6,
        clicks_reported: 6,
        click_through_rate: 0.05,
        read_rate: 0.214,
        engagement_rate: 0.081,
      },
      by_platform: [
        {
          platform: "devto",
          published: 5,
          failed: 0,
          views: 3000,
          engagement: 260,
          engagement_rate: 0.086,
        },
      ],
      by_content_type: [
        {
          content_type: "announcement",
          label: "Announcement",
          publications: 5,
          views: 3000,
          avg_views: 600,
          engagement_rate: 0.086,
        },
      ],
      top_content: [],
      timeline: [],
    };
  }

  beforeEach(() => {
    api.analytics.mockResolvedValue(overview());
    api.engagementTrend.mockResolvedValue([]);
    api.alerts.mockResolvedValue({ alerts: [] });
    api.pipeline.mockResolvedValue({
      content_by_status: [],
      publications: { published: 0, failed: 0, in_flight: 0, cancelled: 0, success_rate: 1 },
      by_platform: [],
    });
    api.activitySummary.mockResolvedValue({
      days: 30, page_views: 0, actions: 0, top_pages: [], top_actions: [], by_day: [],
    });
    api.featureUsage.mockResolvedValue({ days: 30, features: [], unused: [], unmapped_actions: [] });
    api.contentFunnel.mockResolvedValue({
        days: 90, stale_days: 7,
        overall: { written: 0, reached_review: 0, approved: 0, published: 0, dropped: 0, review_rate: null, approval_rate: null, publish_rate: null, overall_rate: null },
        by_origin: [], median_hours_to_publish: null, stuck_in_draft: 0, stuck_in_review: 0, stuck: [],
      });
    api.autopilotEffectiveness.mockResolvedValue({
        days: 90, routed: 0, auto_approved: 0, held: 0, auto_rate: null, inferred: 0, hold_reasons: [],
        held_published: 0, override_rate: null, held_rejected: 0, rejection_rate: null, auto_pulled: 0,
        pulled_rate: null, auto_below_seo_threshold: 0, median_quality_auto: null, median_quality_held: null,
        quality_distribution: [],
      });
    api.subscriberGrowth.mockResolvedValue({
      total: 0, last_30_days: 0, series: [], by_source: [],
    });
  });

  it("loses only the section whose payload lost a field", async () => {
    // `benchmarks` is gone. VelocityPanel reads its `.length` during render,
    // which is a TypeError one component deep — exactly the shape of failure
    // that used to blank the page.
    api.velocity.mockResolvedValue({
      publications: 3,
      early_window_hours: 24,
      fastest: [],
      stalled: [],
    });

    await whileCaught(() => draw(<Analytics />));

    expect(screen.getByRole("alert")).toHaveTextContent(FALLBACK);
    // One section lost, and only one.
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByText("Where it lands")).toBeInTheDocument();
    expect(screen.getByText("Best performing")).toBeInTheDocument();
  });

  it("keeps the counters, which are the numbers the page is read for", async () => {
    api.velocity.mockResolvedValue({ publications: 3, early_window_hours: 24 });

    await whileCaught(() => draw(<Analytics />));

    expect(screen.getByRole("heading", { name: "Analytics" })).toBeInTheDocument();
    expect(screen.getByText("Click-through")).toBeInTheDocument();
    expect(screen.getByText("Read rate")).toBeInTheDocument();
  });

  it("draws the whole page when nothing is missing", async () => {
    api.velocity.mockResolvedValue({
      publications: 0,
      early_window_hours: 24,
      benchmarks: [],
      fastest: [],
      stalled: [],
    });

    await draw(<Analytics />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("the dashboard", () => {
  function payload() {
    return {
      totals: {
        content_count: 4,
        published_count: 3,
        publication_count: 5,
        views: 1200,
        click_through_rate: 0.08,
        engagement: 90,
        engagement_rate: 0.05,
      },
      needs_review: 2,
      failed_publications: [
        { id: 9, platform: "devto", error: "401 Unauthorized" },
      ],
      upcoming: [],
      recent_content: [],
      by_project: [],
      alerts: [],
    };
  }

  it("keeps the queue that needs a human when the analytics panel throws", async () => {
    api.dashboard.mockResolvedValue(payload());
    api.reviewQueue.mockResolvedValue([
      { id: 1, title: "Draft 1", project_name: "Pulse", content_type: "tutorial", confidence: 0.9, status: "review" },
      { id: 2, title: "Draft 2", project_name: "Pulse", content_type: "tutorial", confidence: 0.8, status: "review" },
    ]);

    await whileCaught(() => draw(<Dashboard />));

    expect(screen.getByText("401 Unauthorized")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Analytics/ })).toBeInTheDocument();
  });

  it("does not reach the panel at all on an empty account", async () => {
    api.dashboard.mockResolvedValue({
      ...payload(),
      totals: { ...payload().totals, content_count: 0 },
      needs_review: 0,
      failed_publications: [],
    });

    await draw(<Dashboard />);

    // An empty account gets the first-run checklist where the stats would be.
    expect(screen.getByText("Get your first post out")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("the content editor", () => {
  function content(overrides = {}) {
    return {
      id: 3,
      project_id: 7,
      project_name: "Pulse",
      title: "Saved title",
      body_markdown: "A morning of writing",
      excerpt: "Saved excerpt",
      meta_description: "Saved meta",
      keywords: ["pulse"],
      tags: ["python"],
      cover_image_url: null,
      content_type: "announcement",
      status: "draft",
      word_count: 4,
      read_minutes: 1,
      confidence: 0.9,
      generated_by_model: null,
      updated_at: "2026-07-30T10:00:00Z",
      publications: [],
      seo_issues: [],
      seo_score: 80,
      focus_keyword: "pulse",
      slug: "saved-title",
      canonical_url: null,
      ...overrides,
    };
  }

  beforeEach(() => {
    api.platforms.mockResolvedValue([]);
    api.listPreviewLinks.mockResolvedValue([]);
    api.listRevisions.mockResolvedValue({ items: [], total: 0, retained: 50 });
    api.listLanguages.mockResolvedValue([]);
    api.listTranslations.mockResolvedValue({ items: [], source_language: "en" });
  });

  it("does not take unsaved writing down with a sidebar panel", async () => {
    // No `publications` key at all. PublicationsPanel reads its `.length`.
    const { publications, ...withoutPublications } = content();
    expect(publications).toEqual([]);
    api.getContent.mockResolvedValue(withoutPublications);

    await whileCaught(() => draw(<ContentEditor />));

    expect(screen.getByRole("alert")).toHaveTextContent(FALLBACK);
    // The reason this boundary is worth more than the others on the page.
    expect(screen.getByLabelText(/^Body/i)).toHaveValue("A morning of writing");
    expect(screen.getByLabelText(/^Title/i)).toHaveValue("Saved title");
  });

  it("keeps the other sidebar panels, each behind its own boundary", async () => {
    const { publications, ...withoutPublications } = content();
    api.getContent.mockResolvedValue(withoutPublications);

    await whileCaught(() => draw(<ContentEditor />));

    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "SEO" })).toBeInTheDocument();
  });

  it("shows no fallback when the response is whole", async () => {
    api.getContent.mockResolvedValue(content());

    await draw(<ContentEditor />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Not sent anywhere yet.")).toBeInTheDocument();
  });
});
