import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ContentEditor, { PUBLICATION_POLL_MS, publicationsInFlight, toLocalInput } from "./ContentEditor";
import { api } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { ROUTER_FUTURE } from "../lib/routerFuture";

/**
 * The editor's right-hand column, the publish dialog, and what a published
 * piece is allowed to do.
 *
 * `ContentEditor.test.jsx` is about the writing surface — the buffer, the
 * autosave, the passage edit, the approve. The 1,300-line page also carries
 * five panels down its side and a publish dialog, and those were the untested
 * half: between them they own the SEO fields, the link check's three verdicts,
 * the publications list with its retry, and every rule about which platform you
 * are allowed to send to.
 *
 * Separate file rather than a sixth describe in the existing one, because these
 * need mocks that one does not set (`retryPublication`, populated
 * `publications`, a `platforms` list) and it is already the second-longest test
 * file in the frontend.
 */

vi.mock("../lib/api", () => ({
  api: {
    getContent: vi.fn(),
    platforms: vi.fn(),
    updateContent: vi.fn(),
    approveContent: vi.fn(),
    deleteContent: vi.fn(),
    checkLinks: vi.fn(),
    socialCards: vi.fn(),
    editPassage: vi.fn(),
    listPreviewLinks: vi.fn(),
    createPreviewLink: vi.fn(),
    revokePreviewLink: vi.fn(),
    retryPublication: vi.fn(),
    suggestHeadlines: vi.fn(),
    applyHeadline: vi.fn(),
    headlinePerformance: vi.fn(),
    headlineWinner: vi.fn(),
    adoptHeadlineWinner: vi.fn(),
    unscheduleContent: vi.fn(),
    scheduleSuggestions: vi.fn(),
    publishContent: vi.fn(),
    listRevisions: vi.fn(),
    restoreRevision: vi.fn(),
    suggestTags: vi.fn(),
    listLanguages: vi.fn(),
    listTranslations: vi.fn(),
    translateContent: vi.fn(),
    deleteTranslation: vi.fn(),
  },
}));

const toast = { success: vi.fn(), error: vi.fn() };
vi.mock("../components/ui/Toast", () => ({ useToast: () => toast }));

function content(overrides = {}) {
  return {
    id: 3,
    project_id: 7,
    project_name: "Pulse",
    title: "Saved title",
    body_markdown: "Saved body",
    excerpt: "Saved excerpt",
    meta_description: "Saved meta",
    keywords: ["pulse"],
    tags: ["python"],
    cover_image_url: null,
    content_type: "announcement",
    status: "draft",
    word_count: 2,
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

function publication(overrides = {}) {
  return {
    id: 11,
    platform: "devto",
    status: "published",
    external_url: "https://dev.to/h/saved-title",
    scheduled_for: null,
    error: null,
    ...overrides,
  };
}

/** A platform tile as `GET /platforms` describes one. */
function platform(name, { implemented = true, status = "connected" } = {}) {
  return {
    platform: name,
    display_name: name === "devto" ? "Dev.to" : name === "medium" ? "Medium" : name,
    implemented,
    connection: status ? { status } : null,
  };
}

function draw() {
  return render(
    <MemoryRouter future={ROUTER_FUTURE} initialEntries={["/content/3"]}>
      <Routes>
        <Route path="/content/:contentId" element={<ContentEditor />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Render and wait for the page past its loading state. */
async function open(overrides = {}, platforms = []) {
  api.getContent.mockResolvedValue(content(overrides));
  api.platforms.mockResolvedValue(platforms);
  draw();
  await screen.findByDisplayValue("Saved title");
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  api.getContent.mockResolvedValue(content());
  api.platforms.mockResolvedValue([]);
  api.listPreviewLinks.mockResolvedValue([]);
  api.listRevisions.mockResolvedValue({ items: [], total: 0, retained: 50 });
  api.headlinePerformance.mockResolvedValue([]);
  api.scheduleSuggestions.mockResolvedValue([]);
  api.listLanguages.mockResolvedValue([]);
  api.listTranslations.mockResolvedValue({ items: [], source_language: "en" });
  // The auto-save is on a real 2-second timer in this file, and several tests
  // here type into a field — so on a machine slow enough for the typing itself
  // to outlast the debounce, the timer fires *during* the test rather than
  // being cleared by the unmount after it. An unstubbed `updateContent` then
  // resolves `undefined`, which the editor took for a saved piece and crashed
  // on: a failure with no connection to what the test was about, appearing only
  // under load. Answering the way the server does costs nothing and makes the
  // file's timing irrelevant.
  api.updateContent.mockResolvedValue(content());
});

// --------------------------------------------------------------------------- //
// The SEO panel                                                                //
// --------------------------------------------------------------------------- //

describe("the SEO panel", () => {
  describe("marketing image gallery order", () => {
    const urls = ["https://cdn.test/a.png", "https://cdn.test/b.png", "https://cdn.test/c.png"];
    // The real 2s auto-save can fire mid-test on a loaded machine. Echoing what
    // it was sent keeps it from handing back the original order.
    beforeEach(() => {
      api.updateContent.mockImplementation(async (_id, body) => content(body));
    });

    const order = () =>
      [...document.querySelectorAll("aside img[alt^='Marketing image']")].map((i) =>
        i.getAttribute("src"),
      );

    it("moves an image with the buttons", async () => {
      const user = userEvent.setup();
      await open({ marketing_images: urls });

      await user.click(screen.getByRole("button", { name: "Move image 1 later" }));
      expect(order()).toEqual([urls[1], urls[0], urls[2]]);

      await user.click(screen.getByRole("button", { name: "Move image 3 earlier" }));
      expect(order()).toEqual([urls[1], urls[2], urls[0]]);
    });

    it("cannot move the first image earlier or the last later", async () => {
      await open({ marketing_images: urls });

      expect(screen.getByRole("button", { name: "Move image 1 earlier" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Move image 3 later" })).toBeDisabled();
    });

    it("reorders by dragging one tile onto another", async () => {
      await open({ marketing_images: urls });
      const tiles = [...document.querySelectorAll("aside img[alt^='Marketing image']")].map(
        (i) => i.parentElement,
      );
      const dataTransfer = { setData: vi.fn(), effectAllowed: "" };

      fireEvent.dragStart(tiles[0], { dataTransfer });
      fireEvent.dragOver(tiles[2], { dataTransfer });
      fireEvent.drop(tiles[2], { dataTransfer });

      expect(order()).toEqual([urls[1], urls[2], urls[0]]);
    });

    it("offers no reordering for a single image", async () => {
      await open({ marketing_images: [urls[0]] });

      expect(screen.queryByRole("button", { name: /Move image/ })).toBeNull();
    });
  });

  it("explains what a cover image is for while there is no URL to show", async () => {
    await open({ cover_image_url: null });

    expect(screen.getByText(/Must be an absolute URL/i)).toBeInTheDocument();
    expect(document.querySelector("aside img")).toBeNull();
  });

  it("renders the image itself once a URL is typed, which is the real check", async () => {
    // A thumbnail is the same fetch the platforms will make. A text field that
    // merely accepted the string would report a 404 as fine.
    await open({ cover_image_url: "https://cdn.test/cover.png" });

    const img = document.querySelector("aside img");
    expect(img).toHaveAttribute("src", "https://cdn.test/cover.png");
    expect(screen.queryByText(/Must be an absolute URL/i)).not.toBeInTheDocument();
  });

  it("says so when the URL does not load an image", async () => {
    await open({ cover_image_url: "https://cdn.test/missing.png" });

    fireEvent.error(document.querySelector("aside img"));

    expect(await screen.findByText(/did not load an image/i)).toBeInTheDocument();
  });

  it("re-tries the thumbnail after the URL is edited rather than staying broken", async () => {
    // Without clearing the flag, one typo would leave the panel claiming every
    // subsequent URL is broken without ever having fetched it.
    const user = userEvent.setup();
    await open({ cover_image_url: "https://cdn.test/missing.png" });
    fireEvent.error(document.querySelector("aside img"));
    await screen.findByText(/did not load an image/i);

    await user.type(screen.getByLabelText("Cover image"), "x");

    expect(screen.queryByText(/did not load an image/i)).not.toBeInTheDocument();
    expect(document.querySelector("aside img")).toBeInTheDocument();
  });

  it("counts the meta description against the length Google truncates at", async () => {
    await open({ meta_description: "Twelve chars" });

    expect(screen.getByText("12/155")).toBeInTheDocument();
  });

  it("recounts as you type rather than reporting the last save", async () => {
    const user = userEvent.setup();
    await open({ meta_description: "" });

    await user.type(screen.getByLabelText("Meta description"), "abcde");

    expect(screen.getByText("5/155")).toBeInTheDocument();
  });

  it("says there are no issues rather than showing an empty list", async () => {
    await open({ seo_issues: [] });

    expect(screen.getByText("No SEO issues.")).toBeInTheDocument();
  });

  it("lists every issue the server reported", async () => {
    await open({
      seo_issues: [
        { level: "error", message: "No focus keyword." },
        { level: "warning", message: "Title is long." },
      ],
    });

    expect(screen.getByText("No focus keyword.")).toBeInTheDocument();
    expect(screen.getByText("Title is long.")).toBeInTheDocument();
    expect(screen.queryByText("No SEO issues.")).not.toBeInTheDocument();
  });

  it("distinguishes an error from a warning, which is the only reason level is sent", async () => {
    await open({
      seo_issues: [
        { level: "error", message: "No focus keyword." },
        { level: "warning", message: "Title is long." },
      ],
    });

    expect(screen.getByText("No focus keyword.").className).toMatch(/bad/);
    expect(screen.getByText("Title is long.").className).toMatch(/warn/);
  });

  it("seeds the list fields from the arrays the API sends", async () => {
    await open({ keywords: ["pulse", "ci"], tags: ["python", "devops"] });

    expect(screen.getByLabelText("Keywords")).toHaveValue("pulse, ci");
    expect(screen.getByLabelText("Platform tags")).toHaveValue("python, devops");
  });
});

// --------------------------------------------------------------------------- //
// The link check                                                               //
// --------------------------------------------------------------------------- //

describe("the link check", () => {
  const checkButton = () => screen.getByRole("button", { name: /^Check$/ });

  it("does not run on load, because a draft has links you are still typing", async () => {
    await open();

    expect(api.checkLinks).not.toHaveBeenCalled();
    expect(screen.getByText(/invent plausible documentation URLs/i)).toBeInTheDocument();
  });

  it("checks on demand and then offers to re-check", async () => {
    const user = userEvent.setup();
    api.checkLinks.mockResolvedValue({ checked: 1, broken_count: 0, links: [] });
    await open();

    await user.click(checkButton());

    expect(api.checkLinks).toHaveBeenCalledWith(3);
    expect(await screen.findByRole("button", { name: "Re-check" })).toBeInTheDocument();
  });

  it("says a body with no links has none, rather than showing nothing", async () => {
    const user = userEvent.setup();
    api.checkLinks.mockResolvedValue({ checked: 0, broken_count: 0, links: [] });
    await open();

    await user.click(checkButton());

    expect(await screen.findByText("No links in the body.")).toBeInTheDocument();
  });

  it("reports a clean run in the singular for one link", async () => {
    const user = userEvent.setup();
    api.checkLinks.mockResolvedValue({
      checked: 1,
      broken_count: 0,
      links: [{ url: "https://a.test", status: "ok", http_status: 200 }],
    });
    await open();

    await user.click(checkButton());

    expect(await screen.findByText("1 link, none dead.")).toBeInTheDocument();
  });

  it("pluralises a clean run of several", async () => {
    const user = userEvent.setup();
    api.checkLinks.mockResolvedValue({
      checked: 3,
      broken_count: 0,
      links: [{ url: "https://a.test", status: "ok", http_status: 200 }],
    });
    await open();

    await user.click(checkButton());

    expect(await screen.findByText("3 links, none dead.")).toBeInTheDocument();
  });

  it("leads with the dead count when there is one", async () => {
    const user = userEvent.setup();
    api.checkLinks.mockResolvedValue({
      checked: 4,
      broken_count: 2,
      links: [{ url: "https://a.test", status: "broken", detail: "404" }],
    });
    await open();

    await user.click(checkButton());

    expect(await screen.findByText("2 of 4 dead.")).toBeInTheDocument();
  });

  it("keeps 'unknown' separate from 'broken', which is the whole point", async () => {
    // Only a 404 or 410 is a fact. A timeout is the checker failing, not the
    // link, and colouring them the same would send people to fix working URLs.
    const user = userEvent.setup();
    api.checkLinks.mockResolvedValue({
      checked: 2,
      broken_count: 1,
      links: [
        { url: "https://gone.test", status: "broken", detail: "404 Not Found" },
        { url: "https://slow.test", status: "unknown", detail: "Timed out" },
      ],
    });
    await open();

    await user.click(checkButton());

    const dead = (await screen.findByText("https://gone.test")).closest("li");
    const unsure = screen.getByText("https://slow.test").closest("li");
    expect(dead.className).toMatch(/bad/);
    expect(unsure.className).toMatch(/warn/);
    expect(unsure.className).not.toMatch(/bad/);
  });

  it("sorts the dead to the top and the fine ones to the bottom", async () => {
    const user = userEvent.setup();
    api.checkLinks.mockResolvedValue({
      checked: 3,
      broken_count: 1,
      links: [
        { url: "https://fine.test", status: "ok", http_status: 200 },
        { url: "https://slow.test", status: "unknown", detail: "Timed out" },
        { url: "https://gone.test", status: "broken", detail: "404 Not Found" },
      ],
    });
    await open();

    await user.click(checkButton());
    await screen.findByText("https://gone.test");

    const urls = [...document.querySelectorAll("aside li span.font-mono")]
      .map((node) => node.textContent)
      .filter((text) => text.startsWith("https://"));
    expect(urls).toEqual([
      "https://gone.test",
      "https://slow.test",
      "https://fine.test",
    ]);
  });

  it("shows the HTTP status for a link that is fine and the detail otherwise", async () => {
    const user = userEvent.setup();
    api.checkLinks.mockResolvedValue({
      checked: 2,
      broken_count: 1,
      links: [
        { url: "https://fine.test", status: "ok", http_status: 301 },
        { url: "https://gone.test", status: "broken", detail: "404 Not Found" },
      ],
    });
    await open();

    await user.click(checkButton());

    expect(await screen.findByText("OK (301)")).toBeInTheDocument();
    expect(screen.getByText("404 Not Found")).toBeInTheDocument();
  });

  it("says it is checking while the request is out", async () => {
    const user = userEvent.setup();
    let release;
    api.checkLinks.mockReturnValue(new Promise((resolve) => (release = resolve)));
    await open();

    await user.click(checkButton());

    expect(await screen.findByRole("button", { name: "Checking…" })).toBeDisabled();

    await act(async () => release({ checked: 0, broken_count: 0, links: [] }));
  });

  it("reports a failed check in the panel rather than losing it", async () => {
    const user = userEvent.setup();
    api.checkLinks.mockRejectedValue(new Error("Checker unavailable"));
    await open();

    await user.click(checkButton());

    expect(await screen.findByText("Link check failed: Checker unavailable")).toBeInTheDocument();
    // The explanation gives way to the error rather than sitting above it.
    expect(
      screen.queryByText(/invent plausible documentation URLs/i),
    ).not.toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- //
// The publications panel                                                       //
// --------------------------------------------------------------------------- //

describe("the publications panel", () => {
  it("can call off a scheduled piece, after confirming", async () => {
    const scheduled = publication({
      id: 12,
      status: "scheduled",
      external_url: null,
      scheduled_for: "2026-08-20T09:00:00Z",
    });
    api.unscheduleContent.mockResolvedValue([{ ...scheduled, status: "cancelled" }]);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    await open({ publications: [scheduled] });

    await user.click(screen.getByRole("button", { name: "Cancel schedule" }));

    expect(confirm).toHaveBeenCalled();
    expect(api.unscheduleContent).toHaveBeenCalledWith(3);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Schedule cancelled — it will not go out"));
    confirm.mockRestore();
  });

  it("does nothing if the confirmation is declined", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    await open({ publications: [publication({ id: 12, status: "pending", external_url: null })] });

    await user.click(screen.getByRole("button", { name: "Cancel schedule" }));

    expect(api.unscheduleContent).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("offers no cancel once nothing is waiting to go out", async () => {
    await open({ publications: [publication()] }); // published

    expect(screen.queryByRole("button", { name: "Cancel schedule" })).not.toBeInTheDocument();
  });

  it("says nothing has been sent rather than showing an empty list", async () => {
    await open({ publications: [] });

    expect(screen.getByText("Not sent anywhere yet.")).toBeInTheDocument();
  });

  it("names the platform and links to where it went", async () => {
    await open({ publications: [publication()] });

    const link = screen.getByRole("link", { name: "https://dev.to/h/saved-title" });
    expect(link).toHaveAttribute("href", "https://dev.to/h/saved-title");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("shows the scheduled time only while it is still scheduled", async () => {
    // A row that published at noon should not still be advertising the time it
    // was going to go out.
    await open({
      publications: [
        publication({
          id: 12,
          status: "scheduled",
          external_url: null,
          scheduled_for: "2026-08-20T09:00:00Z",
        }),
      ],
    });

    expect(document.querySelector("aside")).toHaveTextContent(
      formatDateTime("2026-08-20T09:00:00Z"),
    );
  });

  it("does not show a scheduled time on a row that already went out", async () => {
    await open({
      publications: [
        publication({ status: "published", scheduled_for: "2026-08-20T09:00:00Z" }),
      ],
    });

    expect(document.querySelector("aside")).not.toHaveTextContent(
      formatDateTime("2026-08-20T09:00:00Z"),
    );
  });

  it("shows the platform's own refusal, which is what tells you what to change", async () => {
    await open({
      publications: [
        publication({
          status: "failed",
          external_url: null,
          error: "422: tag list too long",
        }),
      ],
    });

    expect(screen.getByText("422: tag list too long")).toBeInTheDocument();
  });

  it("offers Retry on a failed row and nowhere else", async () => {
    await open({
      publications: [
        publication({ id: 11, status: "published" }),
        publication({ id: 12, platform: "medium", status: "failed", error: "500" }),
      ],
    });

    expect(screen.getAllByRole("button", { name: "Retry" })).toHaveLength(1);
  });

  it("retries the row it was clicked on, then re-reads the piece", async () => {
    const user = userEvent.setup();
    api.retryPublication.mockResolvedValue({});
    await open({
      publications: [
        publication({ id: 12, platform: "medium", status: "failed", error: "500" }),
      ],
    });
    api.getContent.mockClear();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(api.retryPublication).toHaveBeenCalledWith(3, 12));
    // Re-read, or the row keeps saying "failed" over a publication now queued.
    await waitFor(() => expect(api.getContent).toHaveBeenCalled());
    // Here, not "check the publish queue": the panel is where the result lands.
    expect(toast.success).toHaveBeenCalledWith("Retrying on Medium — the result will show here");
  });

  it("points a failure on a broken connection at Settings, where the fix is", async () => {
    await open(
      {
        publications: [
          publication({ id: 12, status: "failed", error: "Dev.to rejected the credentials (401)" }),
          publication({ id: 13, platform: "medium", status: "failed", error: "500" }),
        ],
      },
      [platform("devto", { status: "invalid" }), platform("medium")],
    );

    const link = screen.getByRole("link", { name: /Reconnect Dev.to in Settings/ });
    expect(link).toHaveAttribute("href", "/settings");
    // Medium's connection is fine: its failure is not a Settings problem.
    expect(screen.queryByRole("link", { name: /Reconnect Medium/ })).toBeNull();
  });

  it("asks before retrying a post that may already be live", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await open({
      publications: [
        publication({
          id: 12,
          platform: "medium",
          status: "failed",
          error: "read timeout — the request reached Medium, so it may already have gone out. Check Medium before retrying.",
          outcome_unknown: true,
        }),
      ],
    });

    await user.click(screen.getByRole("button", { name: "Checked — retry" }));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("may already be live on Medium"));
    expect(api.retryPublication).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    api.retryPublication.mockResolvedValue({});
    await user.click(screen.getByRole("button", { name: "Checked — retry" }));
    await waitFor(() => expect(api.retryPublication).toHaveBeenCalledWith(3, 12));
    confirm.mockRestore();
  });

  it("does not ask before an ordinary retry", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm");
    api.retryPublication.mockResolvedValue({});
    await open({
      publications: [publication({ id: 12, status: "failed", error: "500", outcome_unknown: false })],
    });

    await user.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(api.retryPublication).toHaveBeenCalled());
    expect(confirm).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("reports a retry the server refused instead of claiming it worked", async () => {
    const user = userEvent.setup();
    api.retryPublication.mockRejectedValue(new Error("Still rate limited"));
    await open({
      publications: [
        publication({ id: 12, platform: "medium", status: "failed", error: "500" }),
      ],
    });

    await user.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Publication retry failed: Still rate limited"));
    expect(toast.success).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------------------------- //
// The publish dialog                                                           //
// --------------------------------------------------------------------------- //

describe("the publish dialog", () => {
  async function openDialog(overrides = {}, platforms = [platform("devto")]) {
    const user = userEvent.setup();
    await open(overrides, platforms);
    await user.click(screen.getByRole("button", { name: "Publish" }));
    await screen.findByRole("heading", { name: "Publish" });
    return user;
  }

  it("suggests when to publish to what is ticked, and fills the time in", async () => {
    api.scheduleSuggestions.mockResolvedValue([
      { platform: "devto", when: "2026-11-03T13:00:00Z", rationale: "Dev.to: Tue–Thu at 13:00 UTC" },
    ]);
    api.publishContent.mockResolvedValue([]);
    const user = await openDialog();
    // Nothing ticked, nothing to suggest for.
    expect(api.scheduleSuggestions).not.toHaveBeenCalled();

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(await screen.findByRole("button", { name: /Dev\.to: Tue–Thu/ }));

    expect(api.scheduleSuggestions).toHaveBeenCalledWith(3, ["devto"]);
    expect(screen.getByLabelText(/When/)).toHaveValue(toLocalInput("2026-11-03T13:00:00Z"));
    await user.click(screen.getByRole("button", { name: "Schedule" }));
    await waitFor(() =>
      expect(api.publishContent).toHaveBeenCalledWith(
        3,
        expect.objectContaining({ platforms: ["devto"], scheduled_for: "2026-11-03T13:00:00.000Z" }),
      ),
    );
  });

  it("still publishes when no suggestion can be had", async () => {
    api.scheduleSuggestions.mockRejectedValue(new Error("boom"));
    const user = await openDialog();

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));

    expect(screen.getByRole("button", { name: "Publish now" })).toBeEnabled();
    expect(screen.queryByText("Suggested")).not.toBeInTheDocument();
  });

  it("will not publish with nothing selected", async () => {
    await openDialog();

    expect(screen.getByRole("button", { name: "Publish now" })).toBeDisabled();
  });

  it("enables the button once a platform is ticked", async () => {
    const user = await openDialog();

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));

    expect(screen.getByRole("button", { name: "Publish now" })).toBeEnabled();
  });

  it("shows an unfinished adapter rather than hiding it, with the reason", async () => {
    // Hiding it makes the list look arbitrary — a user who expects Medium and
    // does not see it assumes Pulse is broken.
    await openDialog({}, [platform("medium", { implemented: false })]);

    expect(screen.getByText("Adapter not finished")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Medium/ })).toBeDisabled();
  });

  it("points an unconnected platform at where the credentials go", async () => {
    await openDialog({}, [platform("devto", { status: null })]);

    expect(
      screen.getByText("Not connected — add credentials in Settings"),
    ).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Dev\.to/ })).toBeDisabled();
  });

  it("offers a Connect link to Settings only where a connection is missing", async () => {
    await openDialog({}, [
      platform("devto", { status: null }),
      platform("medium", { implemented: false }),
    ]);

    const connect = screen.getByRole("link", { name: "Connect Dev.to" });
    expect(connect).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("link", { name: /Connect Medium/ })).toBeNull();
  });

  it("refuses a platform this piece is already live on", async () => {
    await openDialog(
      { publications: [publication({ platform: "devto", status: "published" })] },
      [platform("devto")],
    );

    expect(screen.getByText("Already published here")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Dev\.to/ })).toBeDisabled();
  });

  it("still offers a platform whose last attempt failed", async () => {
    // Only a *published* publication blocks. A failed one is precisely what the
    // dialog is being opened to fix.
    await openDialog(
      { publications: [publication({ platform: "devto", status: "failed" })] },
      [platform("devto")],
    );

    expect(screen.queryByText("Already published here")).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Dev\.to/ })).toBeEnabled();
  });

  it("says 'already published' ahead of the other reasons for the same tile", async () => {
    // All three can be true at once; the one that is about *this piece* is the
    // one worth reading.
    await openDialog(
      { publications: [publication({ platform: "devto", status: "published" })] },
      [platform("devto", { implemented: false, status: null })],
    );

    expect(screen.getByText("Already published here")).toBeInTheDocument();
    expect(screen.queryByText("Adapter not finished")).not.toBeInTheDocument();
  });

  it("sends the ticked platforms, publishing now when no time is given", async () => {
    const user = await openDialog({}, [platform("devto"), platform("medium")]);
    api.publishContent.mockResolvedValue({});

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(screen.getByRole("checkbox", { name: /Medium/ }));
    await user.click(screen.getByRole("button", { name: "Publish now" }));

    await waitFor(() => expect(api.publishContent).toHaveBeenCalled());
    expect(api.publishContent.mock.calls[0][1]).toMatchObject({
      platforms: ["devto", "medium"],
      scheduled_for: null,
      as_draft: false,
      allow_broken_links: false,
    });
  });

  it("un-ticking removes a platform rather than sending it twice", async () => {
    const user = await openDialog({}, [platform("devto"), platform("medium")]);
    api.publishContent.mockResolvedValue({});

    const devto = screen.getByRole("checkbox", { name: /Dev\.to/ });
    await user.click(devto);
    await user.click(screen.getByRole("checkbox", { name: /Medium/ }));
    await user.click(devto);
    await user.click(screen.getByRole("button", { name: "Publish now" }));

    await waitFor(() => expect(api.publishContent).toHaveBeenCalled());
    expect(api.publishContent.mock.calls[0][1].platforms).toEqual(["medium"]);
  });

  it("reads the time as local and sends it as an instant", async () => {
    // `datetime-local` has no offset. The browser's own is the only honest
    // reading of what the user typed into it.
    const user = await openDialog();
    api.publishContent.mockResolvedValue({});

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.type(screen.getByLabelText(/^When/), "2026-09-01T09:30");
    await user.click(screen.getByRole("button", { name: "Schedule" }));

    await waitFor(() => expect(api.publishContent).toHaveBeenCalled());
    expect(api.publishContent.mock.calls[0][1].scheduled_for).toBe(
      new Date("2026-09-01T09:30").toISOString(),
    );
  });

  it("calls the button Schedule once a time is set", async () => {
    const user = await openDialog();

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    expect(screen.getByRole("button", { name: "Publish now" })).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^When/), "2026-09-01T09:30");

    expect(screen.getByRole("button", { name: "Schedule" })).toBeInTheDocument();
  });

  it("passes the platform-draft choice through", async () => {
    const user = await openDialog();
    api.publishContent.mockResolvedValue({});

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(screen.getByRole("checkbox", { name: /Create as a draft/ }));
    await user.click(screen.getByRole("button", { name: "Publish now" }));

    await waitFor(() => expect(api.publishContent).toHaveBeenCalled());
    expect(api.publishContent.mock.calls[0][1].as_draft).toBe(true);
  });

  it("closes, re-reads and says so on success", async () => {
    const user = await openDialog();
    api.publishContent.mockResolvedValue({});
    api.getContent.mockClear();

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(screen.getByRole("button", { name: "Publish now" }));

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Publish" })).not.toBeInTheDocument(),
    );
    expect(api.getContent).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith("Queued for publishing");
  });

  it("keeps the dialog open with the selection intact when the server refuses", async () => {
    const user = await openDialog();
    api.publishContent.mockRejectedValue(new Error("Project has no live URL"));

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(screen.getByRole("button", { name: "Publish now" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Project has no live URL"),
    );
    expect(screen.getByRole("heading", { name: "Publish" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Dev\.to/ })).toBeChecked();
    expect(screen.getByRole("button", { name: "Publish now" })).toBeEnabled();
  });

  it("answers a dead-link refusal in the form rather than with a toast", async () => {
    // The override that answers it is a checkbox in this dialog. A toast would
    // name a flag with nothing to click.
    const user = await openDialog();
    api.publishContent.mockRejectedValue(
      new Error(
        "2 dead links: https://gone.test. Fix them, or set allow_broken_links.",
      ),
    );

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(screen.getByRole("button", { name: "Publish now" }));

    expect(await screen.findByRole("checkbox", { name: /Publish anyway/ })).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("drops the server's advice about the flag it just rendered a checkbox for", async () => {
    const user = await openDialog();
    api.publishContent.mockRejectedValue(
      new Error(
        "2 dead links: https://gone.test. Fix them, or set allow_broken_links.",
      ),
    );

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(screen.getByRole("button", { name: "Publish now" }));

    expect(
      await screen.findByText("2 dead links: https://gone.test."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/allow_broken_links/)).not.toBeInTheDocument();
  });

  it("sends the override on the second attempt", async () => {
    const user = await openDialog();
    api.publishContent.mockRejectedValue(
      new Error("2 dead links. Fix them, or set allow_broken_links."),
    );

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(screen.getByRole("button", { name: "Publish now" }));
    await screen.findByRole("checkbox", { name: /Publish anyway/ });

    api.publishContent.mockResolvedValue({});
    await user.click(screen.getByRole("checkbox", { name: /Publish anyway/ }));
    await user.click(screen.getByRole("button", { name: "Publish now" }));

    await waitFor(() => expect(api.publishContent).toHaveBeenCalledTimes(2));
    expect(api.publishContent.mock.calls[1][1].allow_broken_links).toBe(true);
  });

  it("does not send the override until it is ticked", async () => {
    const user = await openDialog();
    api.publishContent.mockRejectedValue(
      new Error("2 dead links. Fix them, or set allow_broken_links."),
    );

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(screen.getByRole("button", { name: "Publish now" }));
    await screen.findByRole("checkbox", { name: /Publish anyway/ });
    await user.click(screen.getByRole("button", { name: "Publish now" }));

    await waitFor(() => expect(api.publishContent).toHaveBeenCalledTimes(2));
    expect(api.publishContent.mock.calls[1][1].allow_broken_links).toBe(false);
  });

  it("cancels without publishing", async () => {
    const user = await openDialog();

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Publish" })).not.toBeInTheDocument(),
    );
    expect(api.publishContent).not.toHaveBeenCalled();
  });

  it("blocks a second submit while the first is in flight", async () => {
    const user = await openDialog();
    let release;
    api.publishContent.mockReturnValue(new Promise((resolve) => (release = resolve)));

    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    await user.click(screen.getByRole("button", { name: "Publish now" }));

    expect(await screen.findByRole("button", { name: "Queueing…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();

    await act(async () => release({}));
  });

  it("copes with a platforms request that has not answered yet", async () => {
    // `platforms ?? []` is the whole guard. Without it the dialog throws on
    // `.map` and takes the editor down with it.
    const user = userEvent.setup();
    api.getContent.mockResolvedValue(content());
    api.platforms.mockReturnValue(new Promise(() => {}));
    draw();
    await screen.findByDisplayValue("Saved title");

    await user.click(screen.getByRole("button", { name: "Publish" }));

    expect(await screen.findByRole("heading", { name: "Publish" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish now" })).toBeDisabled();
  });
});

// --------------------------------------------------------------------------- //
// Write and preview                                                            //
// --------------------------------------------------------------------------- //

describe("the write and preview tabs", () => {
  it("opens on the writing surface", async () => {
    await open();

    expect(screen.getByLabelText("Title")).toBeInTheDocument();
    expect(document.querySelector("article.prose-pulse")).toBeNull();
  });

  it("renders the draft as markdown under preview", async () => {
    const user = userEvent.setup();
    await open({ body_markdown: "## A heading\n\nSome prose." });

    await user.click(screen.getByRole("button", { name: "Preview" }));

    const article = document.querySelector("article.prose-pulse");
    expect(within(article).getByRole("heading", { level: 2 })).toHaveTextContent(
      "A heading",
    );
    expect(article).toHaveTextContent("Some prose.");
  });

  it("previews what is typed, not what was last saved", async () => {
    const user = userEvent.setup();
    await open({ body_markdown: "Saved body" });

    await user.clear(screen.getByLabelText(/^Body/));
    await user.type(screen.getByLabelText(/^Body/), "Unsaved body");
    await user.click(screen.getByRole("button", { name: "Preview" }));

    expect(document.querySelector("article.prose-pulse")).toHaveTextContent(
      "Unsaved body",
    );
  });

  it("escapes the title rather than letting it inject markup", async () => {
    // The title is interpolated into an <h1> outside the markdown renderer, so
    // it needs its own escape — this asserts that escape exists.
    const user = userEvent.setup();
    await open({ title: "Saved title" });

    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "<img onerror=x>");
    await user.click(screen.getByRole("button", { name: "Preview" }));

    const article = document.querySelector("article.prose-pulse");
    expect(article.querySelector("img")).toBeNull();
    expect(article).toHaveTextContent("<img onerror=x>");
  });

  it("goes back to writing with the text intact", async () => {
    const user = userEvent.setup();
    await open();

    await user.type(screen.getByLabelText(/^Body/), " and more");
    await user.click(screen.getByRole("button", { name: "Preview" }));
    await user.click(screen.getByRole("button", { name: "Write" }));

    expect(screen.getByLabelText(/^Body/)).toHaveValue("Saved body and more");
  });
});

// --------------------------------------------------------------------------- //
// A published piece                                                            //
// --------------------------------------------------------------------------- //

describe("a piece that has already gone out", () => {
  it("takes away the controls that would change it", async () => {
    await open({ status: "published" });

    expect(screen.queryByRole("button", { name: /^Save/ })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Delete this piece/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();
  });

  it("makes the editable fields read-only rather than merely ignoring edits", async () => {
    await open({ status: "published" });

    expect(screen.getByLabelText("Title")).toBeDisabled();
    expect(screen.getByLabelText(/^Body/)).toBeDisabled();
    expect(screen.getByLabelText("Meta description")).toBeDisabled();
    expect(screen.getByLabelText("Keywords")).toBeDisabled();
    expect(screen.getByLabelText("Platform tags")).toBeDisabled();
    expect(screen.getByLabelText("Cover image")).toBeDisabled();
    expect(screen.getByLabelText("Excerpt")).toBeDisabled();
  });

  it("does not offer Approve on something already published", async () => {
    await open({ status: "published" });

    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("still offers Approve on a draft and on one in review", async () => {
    await open({ status: "review" });

    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("still shows where it went, which is the reason to open it at all", async () => {
    await open({
      status: "published",
      publications: [publication()],
    });

    expect(
      screen.getByRole("link", { name: "https://dev.to/h/saved-title" }),
    ).toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- //
// History and translations when their data does not arrive                    //
// --------------------------------------------------------------------------- //

describe("a side panel whose load fails", () => {
  it("says the history could not load, instead of 'No earlier versions.'", async () => {
    api.listRevisions.mockRejectedValueOnce(new Error("offline"));
    api.listRevisions.mockResolvedValueOnce({
      items: [{ revision: 2, created_at: "2026-08-01T10:00:00Z", note: "title" }],
      total: 1,
      retained: 50,
    });
    const user = userEvent.setup();
    await open();

    expect(await screen.findByText("Could not load this piece's history.")).toBeInTheDocument();
    expect(screen.queryByText("No earlier versions.")).not.toBeInTheDocument();

    const history = screen.getByRole("heading", { name: "History" }).closest(".panel");
    await user.click(within(history).getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("v2")).toBeInTheDocument();
  });

  it("says the translations could not load, instead of 'No translations yet.'", async () => {
    api.listTranslations.mockRejectedValueOnce(new Error("offline"));
    const user = userEvent.setup();
    await open();

    expect(await screen.findByText("Could not load translations.")).toBeInTheDocument();
    expect(screen.queryByText("No translations yet.")).not.toBeInTheDocument();

    const panel = screen.getByRole("heading", { name: "Translations" }).closest(".panel");
    await user.click(within(panel).getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("No translations yet.")).toBeInTheDocument();
  });

  describe("a translation that did not succeed", () => {
    const row = (over) => ({
      language: "fr",
      name: "French",
      status: "ready",
      stale: false,
      quality_issues: [],
      ...over,
    });

    it.each([
      ["failed", row({ status: "failed" }), "Retry"],
      ["stuck pending", row({ status: "pending" }), "Retry"],
      ["stale", row({ stale: true }), "Update"],
    ])("can be re-run in place when %s", async (_label, item, label) => {
      api.listTranslations
        .mockResolvedValueOnce({ items: [item], source_language: "en" })
        .mockResolvedValue({ items: [row({})], source_language: "en" });
      api.translateContent.mockResolvedValue({});
      const user = userEvent.setup();
      await open();

      const panel = (await screen.findByRole("heading", { name: "Translations" })).closest(".panel");
      await user.click(await within(panel).findByRole("button", { name: label }));

      expect(api.translateContent).toHaveBeenCalledWith(expect.anything(), "fr");
      expect(await within(panel).findByText("Ready")).toBeInTheDocument();
    });

    it("offers no re-run for a translation that is fine", async () => {
      api.listTranslations.mockResolvedValue({ items: [row({})], source_language: "en" });
      await open();

      const panel = (await screen.findByRole("heading", { name: "Translations" })).closest(".panel");
      await within(panel).findByText("Ready");
      expect(within(panel).queryByRole("button", { name: /^(Retry|Update)$/ })).not.toBeInTheDocument();
      expect(within(panel).getByRole("button", { name: "Remove" })).toBeInTheDocument();
    });
  });
});


// --------------------------------------------------------------------------- //
// Headline testing on a live piece                                            //
// --------------------------------------------------------------------------- //

describe("the headline panel", () => {
  it("is not offered while the piece is still a draft", async () => {
    await open({ status: "draft" });

    expect(screen.queryByRole("button", { name: "Suggest alternatives" })).not.toBeInTheDocument();
  });

  it("suggests alternatives for a live piece and swaps one in", async () => {
    api.suggestHeadlines.mockResolvedValue({
      variants: ["Saved title", "Why the retry budget outlasts the outage"],
    });
    api.applyHeadline.mockResolvedValue({ id: 3 });
    const user = userEvent.setup();
    await open({ status: "published" });

    await user.click(screen.getByRole("button", { name: "Suggest alternatives" }));
    // The current title is not offered back as an alternative to itself.
    const use = await screen.findByRole("button", {
      name: "Use “Why the retry budget outlasts the outage”",
    });
    expect(screen.queryByRole("button", { name: "Use “Saved title”" })).not.toBeInTheDocument();

    await user.click(use);

    expect(api.applyHeadline).toHaveBeenCalledWith(3, "Why the retry budget outlasts the outage");
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("shows what each headline earned once there is more than one", async () => {
    api.headlineWinner.mockResolvedValue(null);
    api.headlinePerformance.mockResolvedValue([
      { title: "First headline", started_at: "2026-08-01T00:00:00Z", current: false, views: 1200, engagement: 40 },
      { title: "Saved title", started_at: "2026-08-03T00:00:00Z", current: true, views: 300, engagement: 9 },
    ]);
    await open({ status: "published" });

    expect(await screen.findByText("What each headline earned")).toBeInTheDocument();
    expect(screen.getByText("1,200 views · 40 interactions")).toBeInTheDocument();
  });

  const twoHeadlines = [
    { title: "First headline", started_at: "2026-08-01T00:00:00Z", current: false, views: 1200, engagement: 40 },
    { title: "Saved title", started_at: "2026-08-03T00:00:00Z", current: true, views: 300, engagement: 9 },
  ];

  it("says which headline is winning and adopts it", async () => {
    api.headlinePerformance.mockResolvedValue(twoHeadlines);
    api.headlineWinner.mockResolvedValue({
      title: "First headline",
      confident: true,
      reason: "“First headline” earned 3.1× the views per day of the live one.",
      applied: false,
      ranked: [],
    });
    api.adoptHeadlineWinner.mockResolvedValue({
      title: "First headline", confident: true, reason: "Swapped.", applied: true, ranked: [],
    });
    const user = userEvent.setup();
    await open({ status: "published" });

    expect(await screen.findByText(/earned 3.1× the views per day/)).toBeInTheDocument();
    api.getContent.mockClear();
    await user.click(screen.getByRole("button", { name: "Adopt “First headline”" }));

    expect(api.adoptHeadlineWinner).toHaveBeenCalledWith(3);
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "Now live: “First headline” — the live posts are being retitled",
      ),
    );
    // The piece is re-read, so the editor's title is the new one.
    await waitFor(() => expect(api.getContent).toHaveBeenCalled());
  });

  it("explains a lead too small to act on, and offers no swap", async () => {
    api.headlinePerformance.mockResolvedValue(twoHeadlines);
    api.headlineWinner.mockResolvedValue({
      title: "First headline",
      confident: false,
      reason: "The headline live now has not had a fair run yet — give it time before judging it against the others.",
      applied: false,
      ranked: [],
    });
    await open({ status: "published" });

    expect(await screen.findByText(/has not had a fair run yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Adopt/ })).not.toBeInTheDocument();
  });

  it("can go back to an earlier headline", async () => {
    api.headlinePerformance.mockResolvedValue(twoHeadlines);
    api.headlineWinner.mockResolvedValue(null);
    api.applyHeadline.mockResolvedValue({ id: 3 });
    const user = userEvent.setup();
    await open({ status: "published" });

    await user.click(await screen.findByRole("button", { name: "Go back to “First headline”" }));

    expect(api.applyHeadline).toHaveBeenCalledWith(3, "First headline");
  });

  it("does not ask for a verdict with only one headline to judge", async () => {
    await open({ status: "published" });
    await screen.findByRole("button", { name: "Suggest alternatives" });

    expect(api.headlineWinner).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------------------------- //
// Watching a publish land                                                      //
// --------------------------------------------------------------------------- //

describe("a publication on its way", () => {
  it("counts pending and publishing rows as in flight, and scheduled ones not", () => {
    expect(publicationsInFlight(content({ publications: [publication({ status: "pending" })] }))).toBe(true);
    expect(publicationsInFlight(content({ publications: [publication({ status: "publishing" })] }))).toBe(true);
    expect(publicationsInFlight(content({ publications: [publication({ status: "scheduled" })] }))).toBe(false);
    expect(publicationsInFlight(content())).toBe(false);
    expect(publicationsInFlight(null)).toBe(false);
  });

  it("re-reads the piece until the row settles, so the result shows without a reload", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      await open({
        publications: [publication({ status: "pending", external_url: null })],
      });
      api.getContent.mockClear();
      api.getContent.mockResolvedValue(content({ publications: [publication({ status: "published" })] }));

      await act(() => vi.advanceTimersByTimeAsync(PUBLICATION_POLL_MS));

      expect(api.getContent).toHaveBeenCalledTimes(1);
      expect(await screen.findByText("https://dev.to/h/saved-title")).toBeInTheDocument();

      // Settled: no more polling.
      await act(() => vi.advanceTimersByTimeAsync(PUBLICATION_POLL_MS * 3));
      expect(api.getContent).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
