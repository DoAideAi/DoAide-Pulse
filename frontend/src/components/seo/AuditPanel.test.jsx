import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AuditPanel from "./AuditPanel";
import { api } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  api: { seoAudit: vi.fn(), runSeoAudit: vi.fn() },
}));

const LABELS = {
  missing_og_image: "Missing og:image",
  duplicate_title: "Title shared with other pages",
};

function audit(key, overrides = {}) {
  return {
    key,
    name: key.toUpperCase(),
    domain: `${key}.doaide.com`,
    scanned_at: "2026-10-20T03:00:00Z",
    pages_scanned: 2,
    issue_count: 0,
    error: null,
    counts: {},
    pages: [],
    duplicates: { title: [], description: [] },
    ...overrides,
  };
}

const GST = audit("gst", {
  issue_count: 3,
  counts: { missing_og_image: 1, duplicate_title: 2 },
  pages: [
    { url: "https://gst.doaide.com/", title: "GST", issues: ["missing_og_image", "duplicate_title"], og: {} },
    { url: "https://gst.doaide.com/rates", title: "GST", issues: ["duplicate_title"], og: {} },
  ],
  duplicates: {
    title: [{ value: "GST", urls: ["https://gst.doaide.com/", "https://gst.doaide.com/rates"] }],
    description: [],
  },
});

describe("AuditPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists sites worst first, with issue counts, duplicates and pages", async () => {
    api.seoAudit.mockResolvedValue({
      issue_labels: LABELS,
      sites: [audit("tax"), audit("desk", { scanned_at: null }), GST],
    });
    render(<AuditPanel />);

    const groups = await screen.findAllByRole("group");
    expect(groups.map((g) => g.getAttribute("aria-label"))).toEqual([
      "gst.doaide.com",
      "tax.doaide.com",
      "desk.doaide.com",
    ]);
    const gst = groups[0];
    expect(within(gst).getByText("3 issues")).toBeInTheDocument();
    expect(within(gst).getByRole("list", { name: "Issues by type" })).toHaveTextContent(
      "Title shared with other pages ×2Missing og:image ×1",
    );
    expect(within(gst).getByText("“GST”")).toBeInTheDocument();
    expect(within(gst).getByText("/, /rates")).toBeInTheDocument();
    expect(within(groups[2]).getByText("Not audited yet")).toBeInTheDocument();
  });

  it("scans one site in place", async () => {
    api.seoAudit.mockResolvedValue({ issue_labels: LABELS, sites: [audit("gst", { scanned_at: null })] });
    api.runSeoAudit.mockResolvedValue({ issue_labels: LABELS, sites: [GST] });
    render(<AuditPanel />);

    await userEvent.click(await screen.findByRole("button", { name: "Audit gst.doaide.com" }));
    expect(api.runSeoAudit).toHaveBeenCalledWith("gst");
    expect(await screen.findByText("3 issues")).toBeInTheDocument();
  });

  it("says a full audit was queued", async () => {
    api.seoAudit.mockResolvedValue({ issue_labels: LABELS, sites: [] });
    api.runSeoAudit.mockResolvedValue({ queued: true });
    render(<AuditPanel />);

    await userEvent.click(await screen.findByRole("button", { name: "Audit all" }));
    expect(api.runSeoAudit).toHaveBeenCalledWith(null);
    expect(await screen.findByRole("status")).toHaveTextContent("in the background");
  });
});
