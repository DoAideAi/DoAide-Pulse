import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ActivityPanel, PipelineHealth } from "./PipelinePanels";
import { api } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  api: { pipeline: vi.fn(), activitySummary: vi.fn() },
}));

function pipeline(overrides = {}) {
  return {
    content_by_status: [
      { status: "draft", count: 4 },
      { status: "published", count: 3 },
      { status: "failed", count: 1 },
    ],
    publications: { published: 3, failed: 1, in_flight: 2, cancelled: 0, success_rate: 0.75 },
    by_platform: [
      { platform: "devto", published: 3, failed: 1, in_flight: 0, cancelled: 0, success_rate: 0.75 },
      { platform: "hashnode", published: 0, failed: 0, in_flight: 2, cancelled: 0, success_rate: null },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("pipeline health", () => {
  it("shows the success rate over settled attempts and each status", async () => {
    api.pipeline.mockResolvedValue(pipeline());
    render(<PipelineHealth />);

    expect(await screen.findByText("Publish success")).toBeInTheDocument();
    expect(screen.getAllByText("75.0%").length).toBeGreaterThan(0);
    expect(screen.getByText("3 of 4 attempts")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("3 published · 1 failed")).toBeInTheDocument();
    // Nothing settled on Hashnode yet: a dash, not 0%.
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("says so when nothing has settled rather than showing 0%", async () => {
    api.pipeline.mockResolvedValue(
      pipeline({
        publications: { published: 0, failed: 0, in_flight: 0, cancelled: 0, success_rate: null },
        by_platform: [],
      }),
    );
    render(<PipelineHealth />);

    expect(await screen.findByText("nothing has settled yet")).toBeInTheDocument();
    expect(screen.getByText("Nothing has been sent to a platform yet.")).toBeInTheDocument();
  });

  it("offers a retry when the request fails", async () => {
    api.pipeline.mockRejectedValue(new Error("Service unavailable"));
    render(<PipelineHealth />);
    expect(await screen.findByText(/Service unavailable/)).toBeInTheDocument();
  });
});

describe("activity panel", () => {
  it("lists top pages and actions, and refetches for another window", async () => {
    api.activitySummary.mockResolvedValue({
      days: 30,
      page_views: 5,
      actions: 2,
      top_pages: [{ name: "/content", count: 5 }],
      top_actions: [{ name: "POST /content/:id/approve", count: 2 }],
      by_day: [],
    });
    render(<ActivityPanel />);

    expect(await screen.findByText("/content")).toBeInTheDocument();
    expect(screen.getByText("POST /content/:id/approve")).toBeInTheDocument();
    expect(api.activitySummary).toHaveBeenCalledWith(30);

    await userEvent.click(screen.getByRole("button", { name: "7d" }));
    expect(api.activitySummary).toHaveBeenCalledWith(7);
  });

  it("says when nothing was recorded", async () => {
    api.activitySummary.mockResolvedValue({
      days: 30,
      page_views: 0,
      actions: 0,
      top_pages: [],
      top_actions: [],
      by_day: [],
    });
    render(<ActivityPanel />);
    expect(await screen.findByText("No activity recorded in the last 30 days.")).toBeInTheDocument();
  });
});
