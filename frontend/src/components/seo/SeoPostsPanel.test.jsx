import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SeoPostsPanel, { LINK_DEBOUNCE_MS } from "./SeoPostsPanel";
import { api } from "../../lib/api";
import { ROUTER_FUTURE } from "../../lib/routerFuture";

vi.mock("../../lib/api", () => ({
  api: {
    listProjects: vi.fn(),
    platforms: vi.fn(),
    seoPosts: vi.fn(),
    seoOptimalSlots: vi.fn(),
    seoLinkSuggestions: vi.fn(),
    createContent: vi.fn(),
    scheduleContent: vi.fn(),
  },
}));

const DEVTO = { platform: "devto", display_name: "Dev.to", connection: { status: "connected" } };
const MEDIUM = { platform: "medium", display_name: "Medium", connection: null };

function draw() {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <SeoPostsPanel />
    </MemoryRouter>,
  );
}

async function fillIn(user) {
  await user.type(await screen.findByLabelText("Title"), "File ITR online");
  await user.type(screen.getByLabelText("Target keywords"), "income tax, itr");
  await user.type(screen.getByLabelText("Content (Markdown)"), "Filing income tax is easy.");
}

describe("SeoPostsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listProjects.mockResolvedValue([{ id: 4, name: "Tax" }]);
    api.platforms.mockResolvedValue([DEVTO, MEDIUM]);
    api.seoPosts.mockResolvedValue([]);
    api.seoOptimalSlots.mockResolvedValue([
      { platform: "devto", when: "2026-10-27T13:00:00Z", rationale: "Tue–Thu mornings" },
    ]);
    api.seoLinkSuggestions.mockResolvedValue({ posts: [], products: [] });
    api.createContent.mockResolvedValue({ id: 9, title: "File ITR online" });
    api.scheduleContent.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("offers only connected platforms and previews the best time", async () => {
    draw();
    expect(await screen.findByLabelText("Dev.to")).toBeChecked();
    expect(screen.queryByLabelText("Medium")).not.toBeInTheDocument();
    expect(await screen.findByLabelText("Suggested times")).toHaveTextContent("devto");
    expect(api.seoOptimalSlots).toHaveBeenCalledWith(["devto"]);
  });

  it("creates an seo-tagged piece and schedules it at the optimal time", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByLabelText("Dev.to");
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: "Schedule post" }));

    await waitFor(() => expect(api.scheduleContent).toHaveBeenCalled());
    const payload = api.createContent.mock.calls[0][0];
    expect(payload).toMatchObject({
      project_id: 4,
      title: "File ITR online",
      keywords: ["income tax", "itr"],
      tags: ["seo"],
    });
    expect(api.scheduleContent).toHaveBeenCalledWith(9, { platforms: ["devto"], optimize: true });
    expect(await screen.findByRole("status")).toHaveTextContent("Scheduled");
  });

  it("saves a draft without scheduling", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByLabelText("Dev.to");
    await fillIn(user);
    await user.click(screen.getByLabelText("Save as draft"));
    await user.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(api.createContent).toHaveBeenCalled());
    expect(api.scheduleContent).not.toHaveBeenCalled();
  });

  it("says the draft survived when scheduling fails", async () => {
    api.scheduleContent.mockRejectedValue(new Error("Dev.to is not connected"));
    const user = userEvent.setup();
    draw();
    await screen.findByLabelText("Dev.to");
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: "Schedule post" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Saved as a draft, but scheduling failed: Dev.to is not connected",
    );
  });

  it("inserts a suggested product link into the body", async () => {
    api.seoLinkSuggestions.mockResolvedValue({
      posts: [],
      products: [
        { site_key: "tax", name: "Tax", url: "https://tax.doaide.com/", anchor: "income tax", matched_topics: ["income tax"], score: 2 },
      ],
    });
    const user = userEvent.setup();
    draw();
    await screen.findByLabelText("Dev.to");
    await fillIn(user);

    await user.click(await screen.findByRole("button", { name: "Link Tax" }, { timeout: LINK_DEBOUNCE_MS + 1000 }));
    expect(screen.getByLabelText("Content (Markdown)")).toHaveValue(
      "Filing [income tax](https://tax.doaide.com/) is easy.",
    );
  });

  it("lists the queue with each post's state", async () => {
    api.seoPosts.mockResolvedValue([
      { id: 1, title: "Upcoming", status: "approved", scheduled_for: "2026-10-30T10:00:00Z", published_at: null, focus_keyword: "itr", project_name: "Tax" },
      { id: 2, title: "Live", status: "published", scheduled_for: null, published_at: "2026-10-01T10:00:00Z", focus_keyword: "", project_name: "Tax" },
    ]);
    draw();
    expect(await screen.findByRole("link", { name: "Upcoming" })).toHaveAttribute("href", "/content/1");
    expect(screen.getByText("Scheduled")).toBeInTheDocument();
    expect(screen.getByText("Published")).toBeInTheDocument();
    await act(async () => {});
  });

  // The hints under the fields — "Comma separated.", and the meta description's
  // live length verdict — were plain text beside the input. Sighted users read
  // them as they type; a screen reader announced the field and nothing else,
  // so "Google will cut it off" never reached the people it was for.
  it("ties each hint to its field, so it is read with it", async () => {
    const user = userEvent.setup();
    draw();

    const keywords = await screen.findByLabelText("Target keywords");
    expect(keywords).toHaveAccessibleDescription("Comma separated.");

    const meta = screen.getByLabelText("Meta description");
    expect(meta).toHaveAccessibleDescription(/Aim for \d+–\d+ characters/);
    await user.type(meta, "x".repeat(170));
    expect(meta).toHaveAccessibleDescription(/170 characters — Google will cut it off/);
  });

  it("leaves a field without a hint without a description", async () => {
    draw();
    expect(await screen.findByLabelText("Title")).not.toHaveAttribute("aria-describedby");
  });
});

