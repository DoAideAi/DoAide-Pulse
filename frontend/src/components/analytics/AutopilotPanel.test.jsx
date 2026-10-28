import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AutopilotPanel, holdReasonLabel } from "./AutopilotPanel";
import { api } from "../../lib/api";

vi.mock("../../lib/api", () => ({ api: { autopilotEffectiveness: vi.fn() } }));

function report(overrides = {}) {
  return {
    days: 90,
    routed: 20,
    auto_approved: 12,
    held: 8,
    auto_rate: 0.6,
    inferred: 0,
    hold_reasons: [
      { reason: "seo_score", count: 5 },
      { reason: "dead_links", count: 2 },
      { reason: "not_eligible", count: 1 },
    ],
    held_published: 2,
    override_rate: 0.25,
    held_rejected: 3,
    rejection_rate: 0.375,
    auto_pulled: 1,
    pulled_rate: 1 / 12,
    auto_below_seo_threshold: 0,
    median_quality_auto: 82,
    median_quality_held: 55,
    quality_distribution: [
      { bucket: "0-39", auto: 0, held: 1 },
      { bucket: "40-59", auto: 1, held: 4 },
      { bucket: "60-79", auto: 4, held: 3 },
      { bucket: "80-100", auto: 7, held: 0 },
    ],
    ...overrides,
  };
}

beforeEach(() => vi.clearAllMocks());

describe("autopilot effectiveness", () => {
  it("asks for 90 days", async () => {
    api.autopilotEffectiveness.mockResolvedValue(report());
    render(<AutopilotPanel />);
    await screen.findByText("How autopilot judges");
    expect(api.autopilotEffectiveness).toHaveBeenCalledWith(90);
  });

  it("reads the disagreement in both directions", async () => {
    api.autopilotEffectiveness.mockResolvedValue(report());
    render(<AutopilotPanel />);
    expect(await screen.findByText("60.0%")).toBeInTheDocument();
    expect(screen.getByText("12 of 20 written")).toBeInTheDocument();
    expect(screen.getByText("2 of 8 held — gates too strict?")).toBeInTheDocument();
    expect(screen.getByText("3 of 8 held — the gates were right")).toBeInTheDocument();
    expect(screen.getByText("1 of 12 approved — gates too lenient?")).toBeInTheDocument();
  });

  it("names each hold reason in words", async () => {
    api.autopilotEffectiveness.mockResolvedValue(report());
    render(<AutopilotPanel />);
    expect(await screen.findByRole("img", { name: "SEO score below the bar: 5" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Dead links: 2" })).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Not a candidate (review-only mode or low confidence): 1" }),
    ).toBeInTheDocument();
  });

  it("splits the quality scores by what autopilot decided", async () => {
    api.autopilotEffectiveness.mockResolvedValue(report());
    render(<AutopilotPanel />);
    const row = within(await screen.findByRole("table")).getByRole("row", { name: /80-100/ });
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["7", "0"]);
    expect(screen.getByText("Median 82 approved, 55 held.")).toBeInTheDocument();
  });

  it("says when numbers rest on inferred decisions, or on the SEO waiver", async () => {
    api.autopilotEffectiveness.mockResolvedValue(report({ inferred: 6, auto_below_seo_threshold: 2 }));
    render(<AutopilotPanel />);
    expect(await screen.findByText(/6 of these 20 were written before autopilot recorded/)).toBeInTheDocument();
    expect(screen.getByText(/2 approved below the SEO bar/)).toBeInTheDocument();
  });

  it("stays quiet about either when neither applies", async () => {
    api.autopilotEffectiveness.mockResolvedValue(report());
    render(<AutopilotPanel />);
    await screen.findByText("How autopilot judges");
    expect(screen.queryByText(/recorded its decisions/)).not.toBeInTheDocument();
    expect(screen.queryByText(/below the SEO bar/)).not.toBeInTheDocument();
  });

  it("says autopilot wrote nothing instead of showing a row of dashes", async () => {
    api.autopilotEffectiveness.mockResolvedValue(
      report({ routed: 0, auto_approved: 0, held: 0, auto_rate: null, hold_reasons: [] }),
    );
    render(<AutopilotPanel />);
    expect(await screen.findByText("Autopilot has not written anything in the last 90 days.")).toBeInTheDocument();
    expect(screen.queryByText("Approved on its own")).not.toBeInTheDocument();
  });

  it("offers a retry when it cannot load", async () => {
    api.autopilotEffectiveness.mockRejectedValue(new Error("Service unavailable"));
    render(<AutopilotPanel />);
    expect(await screen.findByText(/Service unavailable/)).toBeInTheDocument();
  });
});

describe("holdReasonLabel", () => {
  it("title-cases a reason it does not know yet", () => {
    expect(holdReasonLabel("new_gate")).toBe("New Gate");
  });
});
