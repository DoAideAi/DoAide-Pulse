/**
 * The project registry: cards for what's registered, a dialog to add or edit
 * one, and the two per-card actions — scan and delete — that talk to the API
 * directly rather than through the dialog.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Projects, { formFromDraft, formatBytes } from "./Projects";
import { api } from "../lib/api";
import { ROUTER_FUTURE } from "../lib/routerFuture";

vi.mock("../lib/api", () => ({
  api: {
    listProjects: vi.fn(),
    createProject: vi.fn(),
    updateProject: vi.fn(),
    deleteProject: vi.fn(),
    scanProject: vi.fn(),
    platforms: vi.fn(),
    listIdeas: vi.fn(),
    writeFromIdea: vi.fn(),
    draftProjectFromDocuments: vi.fn(),
  },
}));

const toast = { success: vi.fn(), error: vi.fn() };
vi.mock("../components/ui/Toast", () => ({ useToast: () => toast }));

function draw() {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <Projects />
    </MemoryRouter>,
  );
}

function project(overrides = {}) {
  return {
    id: 1,
    name: "Pulse",
    description: "A dev-blog autopilot.",
    repo_url: "https://github.com/r2st/DoAide-Pulse",
    repo_full_name: "r2st/DoAide-Pulse",
    live_url: "",
    tech_stack: ["FastAPI", "React"],
    target_audience: "",
    keywords: [],
    tone: "technical",
    autopilot_mode: "draft",
    auto_canonical: true,
    canonical_platform: "",
    utm_enabled: true,
    utm_campaign: "",
    slug: "pulse",
    content_count: 4,
    published_count: 3,
    last_scanned_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listProjects.mockResolvedValue([]);
  api.listIdeas.mockResolvedValue([]);
  api.platforms.mockResolvedValue([
    { platform: "devto", display_name: "Dev.to", implemented: true },
    { platform: "twitter", display_name: "Twitter / X", implemented: false },
  ]);
});

describe("loading, error and empty states", () => {
  it("shows a skeleton before the first response", () => {
    api.listProjects.mockReturnValue(new Promise(() => {}));
    draw();

    expect(screen.getByText("Projects")).toBeInTheDocument();
  });

  it("shows a retryable error on a failed fetch", async () => {
    api.listProjects.mockRejectedValue(new Error("Bad Gateway"));
    draw();

    expect(await screen.findByText("Bad Gateway")).toBeInTheDocument();
  });

  it("invites registering the first project", async () => {
    draw();

    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add your first project" })).toBeInTheDocument();
  });
});

describe("a project card", () => {
  it("shows where its RSS feed is once something is published", async () => {
    api.listProjects.mockResolvedValue([project({ id: 7, published_count: 3 })]);
    draw();

    const link = await screen.findByRole("link", { name: "RSS feed" });
    expect(link).toHaveAttribute("href", `${window.location.origin}/api/v1/projects/7/feed.xml`);
  });

  it("says why an Auto project will never publish on its own, and offers the fix", async () => {
    api.listProjects.mockResolvedValue([
      project({
        autopilot_mode: "auto",
        autopilot_blocked_reason:
          "Autopilot is set to publish on its own but names no platforms, so every piece stops for review.",
      }),
    ]);
    const user = userEvent.setup();
    draw();

    expect(await screen.findByText(/names no platforms/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Fix it" }));
    expect(screen.getByRole("heading", { name: "Edit Pulse" })).toBeInTheDocument();
  });

  it("offers no feed link before anything is published, since the feed is a 404 then", async () => {
    api.listProjects.mockResolvedValue([project({ published_count: 0 })]);
    draw();

    await screen.findByText("0 published");
    expect(screen.queryByRole("link", { name: "RSS feed" })).not.toBeInTheDocument();
  });

  it("shows its name, links and autopilot mode", async () => {
    api.listProjects.mockResolvedValue([project()]);
    draw();

    expect(await screen.findByText("Pulse")).toBeInTheDocument();
    expect(screen.getByText("r2st/DoAide-Pulse")).toBeInTheDocument();
    expect(screen.getByTitle("Autopilot mode")).toHaveTextContent("draft");
  });

  it("falls back to the live URL when there is no repo", async () => {
    api.listProjects.mockResolvedValue([
      project({ repo_full_name: "", live_url: "https://pulse.example.com" }),
    ]);
    draw();

    expect(await screen.findByText("https://pulse.example.com")).toBeInTheDocument();
  });

  it("offers a scan button only when a repo is connected", async () => {
    api.listProjects.mockResolvedValue([project({ repo_full_name: "" })]);
    draw();

    await screen.findByText("Pulse");
    expect(screen.queryByRole("button", { name: "Scan repo" })).not.toBeInTheDocument();
  });

  it("shows content counts", async () => {
    api.listProjects.mockResolvedValue([project()]);
    draw();

    await screen.findByText("Pulse");
    expect(screen.getByText("4 pieces")).toBeInTheDocument();
    expect(screen.getByText("3 published")).toBeInTheDocument();
  });

  it("says '1 piece', not '1 pieces'", async () => {
    api.listProjects.mockResolvedValue([project({ content_count: 1 })]);
    draw();

    await screen.findByText("Pulse");
    expect(screen.getByText("1 piece")).toBeInTheDocument();
  });

  it("colours the badge differently for each autopilot mode", async () => {
    // Three modes, three meanings — off, drafts-for-review, and publishing on
    // its own. A card that showed the last of those in the same neutral grey as
    // "off" would make the one mode worth noticing the one you cannot see.
    api.listProjects.mockResolvedValue([
      project({ id: 1, name: "Off", autopilot_mode: "off" }),
      project({ id: 2, name: "Draft", autopilot_mode: "draft" }),
      project({ id: 3, name: "Auto", autopilot_mode: "auto" }),
    ]);
    draw();

    await screen.findByText("Off");
    const [off, drafting, auto] = screen.getAllByTitle("Autopilot mode");
    expect(off).toHaveTextContent("off");
    expect(auto).toHaveTextContent("auto");
    expect(off.className).not.toBe(auto.className);
    expect(drafting.className).not.toBe(off.className);
    expect(drafting.className).not.toBe(auto.className);
  });

  it("shows when the repo was last scanned, and omits it when never", async () => {
    api.listProjects.mockResolvedValue([
      project({ last_scanned_at: "2026-08-13T09:00:00Z" }),
    ]);
    const { unmount } = draw();
    await screen.findByText("Pulse");

    expect(screen.getByTitle("Last repo scan")).toBeInTheDocument();
    unmount();

    api.listProjects.mockResolvedValue([project({ last_scanned_at: null })]);
    draw();
    await screen.findByText("Pulse");

    expect(screen.queryByTitle("Last repo scan")).not.toBeInTheDocument();
  });
});

describe("a project's ideas", () => {
  it("says the ideas could not load, not 'No ideas yet', and retries", async () => {
    api.listProjects.mockResolvedValue([project()]);
    api.listIdeas.mockRejectedValueOnce(new Error("offline"));
    api.listIdeas.mockResolvedValueOnce([{ id: 7, headline: "Why retries need budgets" }]);
    const user = userEvent.setup();
    draw();

    expect(await screen.findByText("Could not load ideas.")).toBeInTheDocument();
    expect(screen.queryByText("No ideas yet")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Why retries need budgets")).toBeInTheDocument();
  });

  it("does not claim there are none while the list is still loading", async () => {
    api.listProjects.mockResolvedValue([project()]);
    api.listIdeas.mockReturnValue(new Promise(() => {}));
    draw();

    expect(await screen.findByText("Loading ideas…")).toBeInTheDocument();
    expect(screen.queryByText("No ideas yet")).not.toBeInTheDocument();
  });
});

describe("scanning a repo", () => {
  it("reports what the scan found and reloads", async () => {
    api.listProjects.mockResolvedValue([project()]);
    api.scanProject.mockResolvedValue({
      full_name: "r2st/DoAide-Pulse",
      new_commit_count: 3,
      new_release_tag: null,
    });
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");

    await user.click(screen.getByRole("button", { name: "Scan repo" }));

    await vi.waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("r2st/DoAide-Pulse: 3 new commit(s)"),
    );
    expect(api.scanProject).toHaveBeenCalledWith(1);
    expect(api.listProjects).toHaveBeenCalledTimes(2);
  });

  it("mentions the release tag alongside the commit count when one shipped", async () => {
    api.listProjects.mockResolvedValue([project()]);
    api.scanProject.mockResolvedValue({
      full_name: "r2st/DoAide-Pulse",
      new_commit_count: 5,
      new_release_tag: "v2.1.0",
    });
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");

    await user.click(screen.getByRole("button", { name: "Scan repo" }));

    await vi.waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "r2st/DoAide-Pulse: 5 new commit(s), release v2.1.0",
      ),
    );
  });

  it("toasts the error rather than throwing", async () => {
    api.listProjects.mockResolvedValue([project()]);
    api.scanProject.mockRejectedValue(new Error("rate limited"));
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");

    await user.click(screen.getByRole("button", { name: "Scan repo" }));

    expect(await screen.findByRole("button", { name: "Scan repo" })).toBeEnabled();
    expect(toast.error).toHaveBeenCalledWith("Repo scan failed: rate limited");
  });
});

describe("deleting a project", () => {
  let confirmSpy;

  afterEach(() => {
    confirmSpy?.mockRestore();
  });

  it("asks for confirmation naming the project before deleting, then reloads", async () => {
    confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    api.listProjects.mockResolvedValueOnce([project()]).mockResolvedValueOnce([]);
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");

    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining("Pulse"));
    expect(api.deleteProject).toHaveBeenCalledWith(1);
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("does nothing when the confirmation is declined", async () => {
    confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    api.listProjects.mockResolvedValue([project()]);
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");

    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(api.deleteProject).not.toHaveBeenCalled();
    expect(screen.getByText("Pulse")).toBeInTheDocument();
  });

  it("toasts a refused delete and leaves the card where it was", async () => {
    // The server refuses this when something still references the project. The
    // card staying put is the point: a row that vanished and came back on the
    // next reload would read as the delete having half-worked.
    confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    api.listProjects.mockResolvedValue([project()]);
    api.deleteProject.mockRejectedValue(new Error("Project has queued publications"));
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");

    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(toast.error).toHaveBeenCalledWith("Could not delete project: Project has queued publications");
    expect(screen.getByText("Pulse")).toBeInTheDocument();
  });
});

describe("the add/edit dialog", () => {
  it("opens quick add dialog from Add your first project", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByText("No projects yet");

    await user.click(screen.getByRole("button", { name: "Add your first project" }));

    expect(screen.getByRole("heading", { name: "Quick add" })).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("");
  });

  it("puts focus in the first field of the quick add dialog", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByText("No projects yet");

    await user.click(screen.getByRole("button", { name: "Add your first project" }));

    expect(screen.getByLabelText("Name")).toHaveFocus();
  });

  it("closes quick add on Escape and hands focus back to what opened it", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByText("No projects yet");
    const opener = screen.getByRole("button", { name: "Add your first project" });
    await user.click(opener);

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("pre-fills from an existing project when editing", async () => {
    api.listProjects.mockResolvedValue([project()]);
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");

    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByRole("heading", { name: "Edit Pulse" })).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Pulse");
    expect(screen.getByLabelText(/Tech stack/)).toHaveValue("FastAPI, React");
  });

  it("only lists implemented platforms as canonical destinations", async () => {
    api.listProjects.mockResolvedValue([project()]);
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");
    await user.click(screen.getByRole("button", { name: "Edit" }));

    const select = await screen.findByLabelText("Primary destination");
    expect(within(select).getByText("Dev.to")).toBeInTheDocument();
    expect(within(select).queryByText("Twitter / X")).not.toBeInTheDocument();
  });

  it("opens the full dialog from the Advanced button when projects already exist", async () => {
    api.listProjects.mockResolvedValue([project()]);
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");

    await user.click(screen.getByRole("button", { name: "Advanced" }));

    expect(screen.getByRole("heading", { name: "Add a project" })).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("");
  });

  it("reads the nullable URL fields as empty strings rather than uncontrolled inputs", async () => {
    // `repo_url`, `live_url` and `canonical_platform` are the three fields
    // ProjectOut declares nullable. Passing null straight into a value prop
    // makes React drop the input to uncontrolled and warn.
    api.listProjects.mockResolvedValue([
      project({ repo_url: null, live_url: null, canonical_platform: null }),
    ]);
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");

    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByLabelText(/Repo URL/)).toHaveValue("");
    expect(screen.getByLabelText(/Live URL/)).toHaveValue("");
    expect(await screen.findByLabelText("Primary destination")).toHaveValue("");
  });

  it("explains what naming a primary destination changes", async () => {
    api.listProjects.mockResolvedValue([project({ canonical_platform: "devto" })]);
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await screen.findByLabelText("Primary destination");

    expect(screen.getByText(/This destination owns the canonical URL/)).toBeInTheDocument();
    expect(screen.queryByText(/First to publish owns the canonical URL/)).not.toBeInTheDocument();
  });

  it("turning off automatic canonicals disables choosing a destination for one", async () => {
    // The two controls describe one decision. Leaving the select live under an
    // unchecked box invites picking a primary destination that does nothing.
    api.listProjects.mockResolvedValue([project()]);
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");
    await user.click(screen.getByRole("button", { name: "Edit" }));

    const auto = screen.getByLabelText(/Auto-set canonical URL/);
    expect(auto).toBeChecked();
    expect(await screen.findByLabelText("Primary destination")).toBeEnabled();

    await user.click(auto);

    expect(auto).not.toBeChecked();
    expect(screen.getByLabelText("Primary destination")).toBeDisabled();
  });

  it("toggling UTM tagging on enables the campaign name field", async () => {
    api.listProjects.mockResolvedValue([project({ utm_enabled: false })]);
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");
    await user.click(screen.getByRole("button", { name: "Edit" }));

    const utm = screen.getByLabelText(/Tag links with UTM/);
    expect(utm).not.toBeChecked();

    await user.click(utm);

    expect(utm).toBeChecked();
    expect(screen.getByLabelText("Campaign name")).toBeEnabled();
  });

  it("disables the campaign name field until UTM tagging is on", async () => {
    api.listProjects.mockResolvedValue([project({ utm_enabled: false })]);
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");
    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByLabelText("Campaign name")).toBeDisabled();
  });

  it("creates a project from quick add with autopilot defaulting to draft", async () => {
    api.createProject.mockResolvedValue(project());
    const user = userEvent.setup();
    draw();
    await screen.findByText("No projects yet");
    await user.click(screen.getByRole("button", { name: "Add your first project" }));

    await user.type(screen.getByLabelText("Name"), "New Project");
    await user.type(screen.getByLabelText(/URL/), "https://github.com/me/proj");
    await user.click(screen.getByRole("button", { name: "Create project" }));

    expect(api.createProject).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "New Project",
        repo_url: "https://github.com/me/proj",
        autopilot_mode: "draft",
      }),
    );
  });

  it("creates a project via advanced form, splitting comma-separated lists and nulling blank URLs", async () => {
    api.listProjects.mockResolvedValue([project()]);
    api.createProject.mockResolvedValue(project());
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");
    await user.click(screen.getByRole("button", { name: "Advanced" }));

    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "New Project");
    await user.type(screen.getByLabelText(/Tech stack/), "Go, Postgres");
    await user.click(screen.getByRole("button", { name: "Save project" }));

    expect(api.createProject).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "New Project",
        tech_stack: ["Go", "Postgres"],
        repo_url: null,
        live_url: null,
        canonical_platform: null,
      }),
    );
  });

  it("names where Auto publishes, offering only connected, finished platforms", async () => {
    api.platforms.mockResolvedValue([
      { platform: "devto", display_name: "Dev.to", implemented: true, connection: { status: "connected" } },
      { platform: "medium", display_name: "Medium", implemented: true, connection: null },
      { platform: "twitter", display_name: "Twitter / X", implemented: false },
    ]);
    api.listProjects.mockResolvedValue([project()]);
    api.updateProject.mockResolvedValue(project());
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");
    await user.click(screen.getByRole("button", { name: "Edit" }));

    // Not asked while the mode is Draft: there is nothing to publish to.
    expect(screen.queryByText("Autopilot publishes to")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Autopilot"), "auto");

    expect(await screen.findByText(/every piece will wait for your review/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Medium/ })).toBeDisabled();
    expect(screen.queryByRole("checkbox", { name: /Twitter/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Dev\.to/ }));
    expect(screen.queryByText(/every piece will wait for your review/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save project" }));

    expect(api.updateProject).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ autopilot_mode: "auto", autopilot_platforms: ["devto"] }),
    );
  });

  it("updates an existing project instead of creating a new one", async () => {
    api.listProjects.mockResolvedValue([project()]);
    api.updateProject.mockResolvedValue(project());
    const user = userEvent.setup();
    draw();
    await screen.findByText("Pulse");
    await user.click(screen.getByRole("button", { name: "Edit" }));

    await user.click(screen.getByRole("button", { name: "Save project" }));

    expect(api.updateProject).toHaveBeenCalledWith(1, expect.any(Object));
    expect(api.createProject).not.toHaveBeenCalled();
  });

  it("toasts success and closes the quick dialog after saving", async () => {
    api.createProject.mockResolvedValue(project());
    const user = userEvent.setup();
    draw();
    await screen.findByText("No projects yet");
    await user.click(screen.getByRole("button", { name: "Add your first project" }));
    await user.type(screen.getByLabelText("Name"), "New Project");

    await user.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith("Project created — autopilot is drafting content");
  });

  it("keeps the quick dialog open and toasts the error on a failed save", async () => {
    api.createProject.mockRejectedValue(new Error("Name already in use"));
    const user = userEvent.setup();
    draw();
    await screen.findByText("No projects yet");
    await user.click(screen.getByRole("button", { name: "Add your first project" }));
    await user.type(screen.getByLabelText("Name"), "New Project");

    await user.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith("Name already in use");
  });

  it("closes the quick dialog without saving on cancel", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByText("No projects yet");
    await user.click(screen.getByRole("button", { name: "Add your first project" }));

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.createProject).not.toHaveBeenCalled();
  });

  it("switches from quick add to advanced form via More options", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByText("No projects yet");
    await user.click(screen.getByRole("button", { name: "Add your first project" }));
    expect(screen.getByRole("heading", { name: "Quick add" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "More options" }));

    expect(screen.getByRole("heading", { name: "Add a project" })).toBeInTheDocument();
  });
});

/* ---- Creating a project from documents ---- */

function file(name, size = 1200, type = "text/markdown") {
  const f = new File(["x".repeat(Math.min(size, 50))], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
}

function draft(overrides = {}) {
  return {
    name: "Tidewatch",
    description: "Tide alerts for sailors.",
    repo_url: "https://github.com/acme/tidewatch",
    live_url: null,
    tech_stack: ["Python", "FastAPI"],
    target_audience: "Sailors",
    keywords: ["tides"],
    tone: "casual",
    source: "ai",
    documents: [{ filename: "brief.md", characters: 400 }],
    warnings: [],
    ...overrides,
  };
}

describe("creating a project from documents", () => {
  async function openUpload(user) {
    await user.click(await screen.findByRole("button", { name: "From documents" }));
    return screen.getByRole("dialog", { name: "Create project from documents" });
  }

  it("is offered in the header and on the empty state", async () => {
    draw();

    expect(await screen.findByRole("button", { name: "From documents" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create from documents" })).toBeInTheDocument();
  });

  it("accepts the supported document types and lists what was picked", async () => {
    const user = userEvent.setup();
    draw();
    const dialog = await openUpload(user);
    const input = within(dialog).getByLabelText("Choose documents");

    expect(input).toHaveAttribute("accept", expect.stringContaining(".pdf"));
    expect(input).toHaveAttribute("accept", expect.stringContaining(".docx"));
    expect(within(dialog).getByRole("button", { name: "Read and fill in" })).toBeDisabled();

    await user.upload(input, [file("brief.md"), file("deck.pdf", 2_500_000, "application/pdf")]);

    const list = within(dialog).getByRole("list", { name: "Selected documents" });
    expect(within(list).getByText("brief.md")).toBeInTheDocument();
    expect(within(list).getByText("2.4 MB")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Read and fill in" })).toBeEnabled();
  });

  it("takes files dropped onto it", async () => {
    const user = userEvent.setup();
    draw();
    const dialog = await openUpload(user);
    const zone = within(dialog).getByText("Drop files here or click to choose").closest("label");

    fireEvent.drop(zone, { dataTransfer: { files: [file("readme.md")] } });

    expect(within(dialog).getByText("readme.md")).toBeInTheDocument();
  });

  it("removes a picked file, and never keeps the same name twice", async () => {
    const user = userEvent.setup();
    draw();
    const dialog = await openUpload(user);
    const input = within(dialog).getByLabelText("Choose documents");

    await user.upload(input, [file("brief.md")]);
    await user.upload(input, [file("brief.md")]);
    expect(within(dialog).getAllByText("brief.md")).toHaveLength(1);

    await user.click(within(dialog).getByRole("button", { name: "Remove brief.md" }));
    expect(within(dialog).queryByText("brief.md")).not.toBeInTheDocument();
  });

  it("stops at five files", async () => {
    const user = userEvent.setup();
    draw();
    const dialog = await openUpload(user);

    await user.upload(
      within(dialog).getByLabelText("Choose documents"),
      ["a", "b", "c", "d", "e", "f"].map((n) => file(`${n}.md`)),
    );

    expect(within(dialog).getAllByRole("button", { name: /^Remove / })).toHaveLength(5);
  });

  it("refuses more than 10 MB in total before uploading anything", async () => {
    const user = userEvent.setup();
    draw();
    const dialog = await openUpload(user);

    await user.upload(within(dialog).getByLabelText("Choose documents"), [
      file("a.pdf", 6 * 1024 * 1024, "application/pdf"),
      file("b.pdf", 6 * 1024 * 1024, "application/pdf"),
    ]);

    expect(within(dialog).getByText(/keep it under 10 MB/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Read and fill in" })).toBeDisabled();
  });

  it("opens the filled-in project form for checking, and creates only on Save", async () => {
    api.draftProjectFromDocuments.mockResolvedValue(draft());
    api.createProject.mockResolvedValue({ id: 9 });
    const user = userEvent.setup();
    draw();
    const dialog = await openUpload(user);
    const picked = file("brief.md");

    await user.upload(within(dialog).getByLabelText("Choose documents"), [picked]);
    await user.click(within(dialog).getByRole("button", { name: "Read and fill in" }));

    expect(api.draftProjectFromDocuments).toHaveBeenCalledWith([picked]);
    const form = await screen.findByRole("dialog", { name: "Add project" });
    expect(within(form).getByText(/Filled in from/)).toHaveTextContent("brief.md by AI");
    expect(within(form).getByLabelText("Name")).toHaveValue("Tidewatch");
    expect(within(form).getByLabelText(/Tech stack/)).toHaveValue("Python, FastAPI");
    expect(within(form).getByLabelText("Tone")).toHaveValue("casual");
    expect(api.createProject).not.toHaveBeenCalled();

    await user.click(within(form).getByRole("button", { name: "Save project" }));

    await waitFor(() => expect(api.createProject).toHaveBeenCalled());
    const payload = api.createProject.mock.calls[0][0];
    expect(payload).toMatchObject({
      name: "Tidewatch",
      tech_stack: ["Python", "FastAPI"],
      keywords: ["tides"],
      repo_url: "https://github.com/acme/tidewatch",
      live_url: null,
    });
  });

  it("passes the server's warnings on to the form", async () => {
    api.draftProjectFromDocuments.mockResolvedValue(
      draft({ source: "heuristic", warnings: ["AI was unavailable."] }),
    );
    const user = userEvent.setup();
    draw();
    const dialog = await openUpload(user);

    await user.upload(within(dialog).getByLabelText("Choose documents"), [file("brief.md")]);
    await user.click(within(dialog).getByRole("button", { name: "Read and fill in" }));

    const form = await screen.findByRole("dialog", { name: "Add project" });
    expect(within(form).getByText("AI was unavailable.")).toBeInTheDocument();
    expect(within(form).getByText(/Filled in from/)).not.toHaveTextContent("by AI");
  });

  it("stays open with the files when reading fails", async () => {
    api.draftProjectFromDocuments.mockRejectedValue(new Error("deck.pdf: no text found."));
    const user = userEvent.setup();
    draw();
    const dialog = await openUpload(user);

    await user.upload(within(dialog).getByLabelText("Choose documents"), [file("deck.pdf")]);
    await user.click(within(dialog).getByRole("button", { name: "Read and fill in" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Could not read the documents: deck.pdf: no text found.",
      ),
    );
    expect(within(dialog).getByText("deck.pdf")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Read and fill in" })).toBeEnabled();
  });
});

describe("formFromDraft", () => {
  it("joins lists for the comma-separated inputs and blanks nulls", () => {
    const form = formFromDraft(draft());
    expect(form.tech_stack).toBe("Python, FastAPI");
    expect(form.live_url).toBe("");
    expect(form.autopilot_mode).toBe("draft");
  });

  it("falls back to the default tone for one it does not know", () => {
    expect(formFromDraft(draft({ tone: "pirate" })).tone).toBe("technical");
  });
});

describe("formatBytes", () => {
  it("reads like a file size", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});
