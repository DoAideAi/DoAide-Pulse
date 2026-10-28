import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FunnelPanel, formatHours, originLabel } from "./FunnelPanel";
import { api } from "../../lib/api";

vi.mock("../../lib/api", () => ({ api: { contentFunnel: vi.fn() } }));

function steps(overrides = {}) {
  return {
    written: 10,
    reached_review: 8,
    approved: 5,
    published: 4,
    dropped: 2,
    review_rate: 0.8,
    approval_rate: 0.625,
    publish_rate: 0.8,
    overall_rate: 0.4,
    ...overrides,
  };
}

function funnel(overrides = {}) {
  return {
    days: 90,
    stale_days: 7,
    overall: steps(),
    by_origin: [
      { origin: "autopilot", ...steps({ written: 7, published: 3, overall_rate: 3 / 7 }) },
      { origin: "manual", ...steps({ written: 3, published: 1, overall_rate: 1 / 3 }) },
    ],
    median_hours_to_publish: 30,
    stuck_in_draft: 1,
    stuck_in_review: 1,
    stuck: [
      { content_id: 41, title: "A draft nobody finished", status: "draft", origin: "manual", idle_days: 12.4 },
      { content_id: 42, title: "Waiting on a reviewer", status: "review", origin: "autopilot", idle_days: 9.9 },
    ],
    ...overrides,
  };
}

function draw() {
  return render(
    <MemoryRouter>
      <FunnelPanel />
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("content funnel", () => {
  it("asks for 90 days, with a week as stuck", async () => {
    api.contentFunnel.mockResolvedValue(funnel());
    draw();
    await screen.findByText("From draft to published");
    expect(api.contentFunnel).toHaveBeenCalledWith(90, 7);
  });

  it("shows each stage as a share of the one before it", async () => {
    api.contentFunnel.mockResolvedValue(funnel());
    draw();
    expect(await screen.findByRole("img", { name: "Approved: 5" })).toBeInTheDocument();
    expect(screen.getByText("62.5% of the stage before")).toBeInTheDocument();
    expect(screen.getByText("2 archived without being published — rejected in review or withdrawn.")).toBeInTheDocument();
  });

  it("leads with the overall rate, the median time and what is stuck", async () => {
    api.contentFunnel.mockResolvedValue(funnel());
    draw();
    expect(await screen.findByText("40.0%")).toBeInTheDocument();
    expect(screen.getByText("4 of 10")).toBeInTheDocument();
    expect(screen.getByText("30 hours")).toBeInTheDocument();
    expect(screen.getByText("idle over 7 days in draft or review")).toBeInTheDocument();
  });

  it("splits the funnel by origin, in words", async () => {
    api.contentFunnel.mockResolvedValue(funnel());
    draw();
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("rowheader", { name: "Autopilot" })).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "Written by hand" })).toBeInTheDocument();
    expect(within(table).getByText("42.9%")).toBeInTheDocument();
  });

  it("links each stuck piece to its editor", async () => {
    api.contentFunnel.mockResolvedValue(funnel());
    draw();
    const list = await screen.findByRole("list", { name: "Stuck pieces" });
    expect(within(list).getByRole("link", { name: "A draft nobody finished" })).toHaveAttribute(
      "href",
      "/content/41",
    );
    expect(within(list).getByText("Review · 9 days · Autopilot")).toBeInTheDocument();
  });

  it("says nothing was written instead of drawing an empty funnel", async () => {
    api.contentFunnel.mockResolvedValue(
      funnel({ overall: steps({ written: 0, reached_review: 0, approved: 0, published: 0, dropped: 0 }), by_origin: [], stuck: [] }),
    );
    draw();
    expect(await screen.findByText("Nothing was written in the last 90 days.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("offers a retry when it cannot load", async () => {
    api.contentFunnel.mockRejectedValue(new Error("Service unavailable"));
    draw();
    expect(await screen.findByText(/Service unavailable/)).toBeInTheDocument();
  });
});

describe("formatHours", () => {
  it.each([
    [null, "—"],
    [1, "1 hour"],
    [30, "30 hours"],
    [47.6, "48 hours"],
    [84, "3.5 days"],
  ])("%s -> %s", (hours, text) => {
    expect(formatHours(hours)).toBe(text);
  });
});

describe("originLabel", () => {
  it("names the known origins and title-cases the rest", () => {
    expect(originLabel("api")).toBe("API");
    expect(originLabel("calendar_import")).toBe("Calendar Import");
  });
});
