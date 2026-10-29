import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard";
import { api } from "../lib/api";
import { ROUTER_FUTURE } from "../lib/routerFuture";

vi.mock("../lib/api", () => ({
  api: {
    dashboard: vi.fn(),
    readTime: vi.fn(),
    engagementTrend: vi.fn(),
    reviewQueue: vi.fn(),
    approveContent: vi.fn(),
    bulkApprove: vi.fn(),
    listContent: vi.fn(),
    platforms: vi.fn(),
  },
}));

const toast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
vi.mock("../components/ui/Toast", () => ({ useToast: () => toast }));

function draw() {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <Dashboard />
    </MemoryRouter>,
  );
}

function payload(overrides = {}) {
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
    needs_review: 0,
    failed_publications: [],
    upcoming: [],
    recent_content: [],
    by_project: [],
    alerts: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listContent.mockResolvedValue([]);
  api.readTime.mockResolvedValue({ published_pieces: 0 });
  api.engagementTrend.mockResolvedValue({ points: [] });
  api.reviewQueue.mockResolvedValue([]);
  api.platforms.mockResolvedValue([]);
  window.localStorage.clear();
});

describe("an empty account", () => {
  const empty = () =>
    payload({ totals: { ...payload().totals, content_count: 0, published_count: 0 } });

  it("walks through setup instead of showing zeroed stat tiles", async () => {
    api.dashboard.mockResolvedValue(empty());
    draw();

    expect(await screen.findByText("Get your first post out")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add project" })).toHaveAttribute("href", "/projects");
    expect(screen.queryByText("Projects")).not.toBeInTheDocument();
    expect(screen.queryByText("Nothing written yet")).not.toBeInTheDocument();
  });

  it("counts a connected destination as done", async () => {
    api.dashboard.mockResolvedValue(empty());
    api.platforms.mockResolvedValue([
      { platform: "devto", connection: { status: "connected" } },
      { platform: "hashnode", connection: null },
    ]);
    draw();

    expect(await screen.findByTestId("step-destination")).toHaveAttribute("data-done", "true");
  });

  it("falls back to the empty state once setup is hidden", async () => {
    api.dashboard.mockResolvedValue(empty());
    draw();

    await userEvent.click(await screen.findByRole("button", { name: "Hide" }));
    expect(screen.getByText("Nothing written yet")).toBeInTheDocument();
  });
});

describe("the stat tiles", () => {
  it("show reach and engagement alongside the counts", async () => {
    api.dashboard.mockResolvedValue(payload());
    draw();

    expect(await screen.findByText("Views")).toBeInTheDocument();
    expect(screen.getByText((1200).toLocaleString())).toBeInTheDocument();
    expect(screen.getByText("Engagement rate")).toBeInTheDocument();
    expect(screen.getByText("5.0%")).toBeInTheDocument();
  });
});

describe("loading and errors", () => {
  it("shows a skeleton before the first response arrives", () => {
    api.dashboard.mockReturnValue(new Promise(() => {}));
    api.reviewQueue.mockReturnValue(new Promise(() => {}));
    api.platforms.mockReturnValue(new Promise(() => {}));
    draw();

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });

  it("shows a retryable error instead of crashing on a failed fetch", async () => {
    api.dashboard.mockRejectedValue(new Error("Service Unavailable"));
    draw();

    expect(await screen.findByText("Service Unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("quick stats bar", () => {
  it("renders project count, published, in review, and scheduled stats", async () => {
    api.dashboard.mockResolvedValue(
      payload({
        by_project: [
          { project_id: 1, name: "Pulse", published: 5, views: 900 },
          { project_id: 2, name: "Jobs", published: 2, views: 100 },
        ],
        upcoming: [
          { id: 1, content_id: 5, title: "Post", platform: "devto", scheduled_for: "2099-01-01T10:00:00Z" },
        ],
      }),
    );
    api.reviewQueue.mockResolvedValue([]);
    draw();

    expect(await screen.findByText("Projects")).toBeInTheDocument();
    expect(screen.getAllByText("Published").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("In Review").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Scheduled").length).toBeGreaterThanOrEqual(1);
  });
});

describe("review queue preview", () => {
  it("shows review cards with approve buttons when items are in review", async () => {
    api.dashboard.mockResolvedValue(payload({ needs_review: 2 }));
    api.reviewQueue.mockResolvedValue([
      {
        id: 1,
        title: "Draft article one",
        project_name: "Pulse",
        content_type: "tutorial",
        confidence: 0.85,
        status: "review",
      },
      {
        id: 2,
        title: "Draft article two",
        project_name: "Jobs",
        content_type: "announcement",
        confidence: 0.6,
        status: "review",
      },
    ]);
    draw();

    expect(await screen.findByText("Draft article one")).toBeInTheDocument();
    expect(screen.getByText("Draft article two")).toBeInTheDocument();
    const approveButtons = screen.getAllByRole("button", { name: "Approve" });
    expect(approveButtons.length).toBe(2);
  });

  it("calls approveContent when the approve button is clicked", async () => {
    api.dashboard.mockResolvedValue(payload({ needs_review: 1 }));
    api.reviewQueue.mockResolvedValue([
      {
        id: 42,
        title: "Approve me",
        project_name: "Pulse",
        content_type: "tutorial",
        confidence: 0.9,
        status: "review",
      },
    ]);
    api.approveContent.mockResolvedValue({});
    draw();

    const approveBtn = await screen.findByRole("button", { name: "Approve" });
    await userEvent.click(approveBtn);

    expect(api.approveContent).toHaveBeenCalledWith(42);
    expect(toast.success).toHaveBeenCalledWith("Approved");
  });

  function oneInReview() {
    api.dashboard.mockResolvedValue(payload({ needs_review: 1 }));
    api.reviewQueue.mockResolvedValue([
      {
        id: 42,
        title: "Approve me",
        project_name: "Pulse",
        content_type: "tutorial",
        confidence: 0.85,
        status: "review",
      },
    ]);
  }

  it("shows the SEO preflight issues and approves anyway with force", async () => {
    oneInReview();
    api.approveContent
      .mockRejectedValueOnce(
        Object.assign(
          new Error(
            "SEO preflight failed — fix these before approving:\n" +
              "• Title is 64 chars — aim for 50–60 for search results.\n" +
              "• Only 0 link(s) in the body — include at least 2 internal links.",
          ),
          { status: 409 },
        ),
      )
      .mockResolvedValueOnce({});
    draw();

    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/Title is 64 chars/)).toBeInTheDocument();
    expect(within(alert).getByText(/Only 0 link/)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Approve anyway" }));

    expect(api.approveContent).toHaveBeenLastCalledWith(42, { force: true });
    expect(toast.success).toHaveBeenCalledWith("Approved");
  });

  it("reports any other refusal instead of swallowing it", async () => {
    oneInReview();
    api.approveContent.mockRejectedValue(
      Object.assign(new Error("This piece is already published"), { status: 409 }),
    );
    draw();

    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(toast.error).toHaveBeenCalledWith(
      "Could not approve: This piece is already published",
    );
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
  });
});

describe("quick actions bar", () => {
  it("renders the floating quick actions toolbar", async () => {
    api.dashboard.mockResolvedValue(payload());
    draw();

    expect(await screen.findByRole("toolbar", { name: "Quick actions" })).toBeInTheDocument();
  });

  it("shows approve count when items are in review", async () => {
    api.dashboard.mockResolvedValue(payload({ needs_review: 5 }));
    api.reviewQueue.mockResolvedValue(
      Array.from({ length: 5 }, (_, i) => ({
        id: i + 1,
        title: `Draft ${i}`,
        project_name: "Pulse",
        content_type: "tutorial",
        confidence: 0.9,
        status: "review",
      })),
    );
    draw();

    expect(await screen.findByTitle(/Approve all 5 reviews/)).toBeInTheDocument();
  });
});

describe("recent activity", () => {
  it("lists recent content with status badges", async () => {
    api.dashboard.mockResolvedValue(
      payload({
        recent_content: [
          {
            id: 3,
            title: "A retry budget that outlasts the outage",
            project_name: "Pulse",
            content_type: "changelog",
            created_at: "2026-08-01T10:00:00Z",
            status: "published",
          },
        ],
      }),
    );
    draw();

    expect(
      await screen.findByText("A retry budget that outlasts the outage"),
    ).toBeInTheDocument();
  });
});

describe("failed publications", () => {
  it("lists failed publications with error details", async () => {
    api.dashboard.mockResolvedValue(
      payload({
        failed_publications: [{ id: 1, platform: "devto", error: "401 Unauthorized" }],
      }),
    );
    draw();

    expect(await screen.findByText("401 Unauthorized")).toBeInTheDocument();
  });
});

describe("scheduled items", () => {
  it("lists upcoming publications", async () => {
    api.dashboard.mockResolvedValue(
      payload({
        upcoming: [
          {
            id: 1,
            content_id: 5,
            title: "Shipping the new editor",
            platform: "devto",
            scheduled_for: "2099-01-01T10:00:00Z",
          },
        ],
      }),
    );
    draw();

    expect(await screen.findByText("Shipping the new editor")).toBeInTheDocument();
  });
});

describe("Dashboard published links", () => {
  it("lists the exact published URLs, not just the count", async () => {
    api.dashboard.mockResolvedValue(payload());
    api.listContent.mockResolvedValue([
      {
        id: 7,
        title: "Shipping faster",
        project_name: "Pulse",
        status: "published",
        published_at: "2026-10-01T10:00:00Z",
        publications: [
          { id: 1, platform: "devto", status: "published", external_url: "https://dev.to/pulse/shipping-faster" },
        ],
      },
    ]);
    draw();
    const link = await screen.findByRole("link", { name: "https://dev.to/pulse/shipping-faster" });
    expect(link).toHaveAttribute("href", "https://dev.to/pulse/shipping-faster");
  });
});

describe("a review queue longer than a page", () => {
  // /content/queue/review answers 50 rows by default; the dashboard's own
  // `needs_review` is the count. The page used to count the rows it was given.
  it("counts what is waiting, not what one page of it holds", async () => {
    api.dashboard.mockResolvedValue(payload({ needs_review: 120 }));
    api.reviewQueue.mockResolvedValue(
      Array.from({ length: 6 }, (_, i) => ({
        id: i + 1,
        title: `Draft ${i}`,
        project_name: "Pulse",
        content_type: "tutorial",
        confidence: 0.9,
        status: "review",
      })),
    );
    draw();

    expect(await screen.findByTitle("Approve all 120 reviews")).toBeInTheDocument();
    expect(screen.getByText("In review (120)")).toBeInTheDocument();
    // Only the preview's six rows are asked for.
    expect(api.reviewQueue).toHaveBeenCalledWith({ limit: 6 });
  });
});
