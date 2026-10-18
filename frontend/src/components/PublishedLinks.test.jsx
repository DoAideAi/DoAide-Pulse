import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PublishedLinks, { groupPublished } from "./PublishedLinks";
import { api } from "../lib/api";
import { ROUTER_FUTURE } from "../lib/routerFuture";

vi.mock("../lib/api", () => ({ api: { listContent: vi.fn() } }));

function piece(id, project, publications, extra = {}) {
  return {
    id,
    title: `Post ${id}`,
    project_name: project,
    status: "published",
    published_at: "2026-10-01T10:00:00Z",
    publications,
    ...extra,
  };
}

const pub = (id, platform, url, status = "published") => ({
  id,
  platform,
  status,
  external_url: url,
  published_at: "2026-10-01T10:00:00Z",
});

function draw(props = {}) {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <PublishedLinks {...props} />
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("groupPublished", () => {
  it("groups by project and keeps only live publications", () => {
    const groups = groupPublished([
      piece(1, "Alpha", [pub(1, "devto", "https://dev.to/a"), pub(2, "hashnode", null, "failed")]),
      piece(2, "Beta", [pub(3, "medium", "https://medium.com/b")]),
      piece(3, "Alpha", [pub(4, "devto", null, "failed")]),
    ]);
    expect(groups.map((g) => g.project)).toEqual(["Alpha", "Beta"]);
    expect(groups[0].pieces).toHaveLength(1);
    expect(groups[0].pieces[0].live.map((p) => p.id)).toEqual([1]);
  });
});

describe("PublishedLinks", () => {
  it("shows the exact published URL for every platform, grouped by project", async () => {
    api.listContent.mockResolvedValue([
      piece(1, "Alpha", [
        pub(1, "devto", "https://dev.to/alpha/post-1"),
        pub(2, "hashnode", "https://alpha.hashnode.dev/post-1"),
      ]),
      piece(2, "Beta", [pub(3, "medium", "https://medium.com/@beta/post-2")]),
    ]);
    draw();

    const link = await screen.findByRole("link", { name: "https://dev.to/alpha/post-1" });
    expect(link).toHaveAttribute("href", "https://dev.to/alpha/post-1");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: "https://alpha.hashnode.dev/post-1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://medium.com/@beta/post-2" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Alpha/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Beta/ })).toBeInTheDocument();
    expect(api.listContent).toHaveBeenCalledWith({ status: "published", limit: 100 });
  });

  it("says when a platform returned no link instead of hiding the publication", async () => {
    api.listContent.mockResolvedValue([piece(1, "Alpha", [pub(1, "linkedin", null)])]);
    draw();
    expect(await screen.findByText("No link returned by the platform")).toBeInTheDocument();
  });

  it("caps pieces per project and links to the full list", async () => {
    api.listContent.mockResolvedValue(
      [1, 2, 3].map((id) => piece(id, "Alpha", [pub(id, "devto", `https://dev.to/p${id}`)])),
    );
    draw({ perProject: 2, compact: true });
    expect(await screen.findByText("+1 more →")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "https://dev.to/p3" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All links" })).toHaveAttribute("href", "/publish");
  });

  it("shows an empty state when nothing is published", async () => {
    api.listContent.mockResolvedValue([]);
    draw();
    expect(await screen.findByText("Nothing published yet")).toBeInTheDocument();
  });
});
