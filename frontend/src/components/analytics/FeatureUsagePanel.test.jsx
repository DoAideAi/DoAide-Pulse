import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FeatureUsagePanel } from "./FeatureUsagePanel";
import { api } from "../../lib/api";

vi.mock("../../lib/api", () => ({ api: { featureUsage: vi.fn() } }));

function usage(overrides = {}) {
  return {
    days: 30,
    features: [
      { feature: "writing", label: "Writing", uses: 40, active_days: 12 },
      { feature: "publishing", label: "Publishing", uses: 9, active_days: 1 },
      { feature: "translation", label: "Translation", uses: 0, active_days: 0 },
      { feature: "triggers", label: "Triggers", uses: 0, active_days: 0 },
    ],
    unused: ["translation", "triggers"],
    unmapped_actions: [],
    ...overrides,
  };
}

beforeEach(() => vi.clearAllMocks());

describe("feature usage", () => {
  it("asks for the last 30 days", async () => {
    api.featureUsage.mockResolvedValue(usage());
    render(<FeatureUsagePanel />);
    await screen.findByText("What gets used");
    expect(api.featureUsage).toHaveBeenCalledWith(30);
  });

  it("bars each used feature with its uses and active days", async () => {
    api.featureUsage.mockResolvedValue(usage());
    render(<FeatureUsagePanel />);
    expect(await screen.findByRole("img", { name: "Writing: 40" })).toBeInTheDocument();
    expect(screen.getByText("on 12 days")).toBeInTheDocument();
    expect(screen.getByText("on 1 day")).toBeInTheDocument();
    // An unused feature is not drawn as an empty bar.
    expect(screen.queryByRole("img", { name: /Translation/ })).not.toBeInTheDocument();
  });

  it("names the unused features by label, not by key", async () => {
    api.featureUsage.mockResolvedValue(usage());
    render(<FeatureUsagePanel />);
    const unused = await screen.findByRole("list", { name: "Features not used" });
    expect(within(unused).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Translation",
      "Triggers",
    ]);
  });

  it("says so when every feature has been used", async () => {
    api.featureUsage.mockResolvedValue(usage({ unused: [] }));
    render(<FeatureUsagePanel />);
    expect(await screen.findByText("Every feature has been used.")).toBeInTheDocument();
  });

  it("says nothing was recorded rather than drawing an empty chart", async () => {
    api.featureUsage.mockResolvedValue(
      usage({ features: usage().features.map((f) => ({ ...f, uses: 0, active_days: 0 })) }),
    );
    render(<FeatureUsagePanel />);
    expect(await screen.findByText("Nothing recorded in the last 30 days yet.")).toBeInTheDocument();
  });

  it("offers a retry when it cannot load", async () => {
    api.featureUsage.mockRejectedValue(new Error("Service unavailable"));
    render(<FeatureUsagePanel />);
    expect(await screen.findByText(/Service unavailable/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
