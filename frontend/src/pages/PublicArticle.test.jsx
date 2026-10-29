import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import PublicArticle from "./PublicArticle";

vi.mock("../lib/api", () => ({
  api: {
    publicArticle: vi.fn(),
    subscribe: vi.fn(),
  },
}));

vi.mock("../lib/markdown", () => ({
  renderMarkdown: (md) => `<p>${md}</p>`,
}));

import { api } from "../lib/api";

const wrap = (slug = "test-article") =>
  render(
    <MemoryRouter initialEntries={[`/article/${slug}`]}>
      <Routes>
        <Route path="/article/:slug" element={<PublicArticle />} />
      </Routes>
    </MemoryRouter>,
  );

describe("PublicArticle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a published article", async () => {
    api.publicArticle.mockResolvedValue({
      title: "Test Article",
      slug: "test-article",
      body_markdown: "Hello world",
      excerpt: "An excerpt",
      meta_description: "A description",
      tags: ["python"],
      word_count: 100,
      read_minutes: 1,
      project_name: "My Project",
      published_at: "2026-10-01T00:00:00",
    });
    wrap();
    expect(await screen.findByText("Test Article")).toBeInTheDocument();
    expect(screen.getByText(/My Project ·/)).toBeTruthy();
    // The date with its month in words, not 10/1/2026 or 1/10/2026.
    expect(screen.getByText(/My Project ·/).textContent).toMatch(/Oct.*2026/);
    expect(screen.getByText(/My Project ·/).textContent).not.toMatch(/\d+\/\d+\/\d+/);
    expect(screen.getByText("Share this article")).toBeInTheDocument();
    expect(screen.getByText("Try DoAide Pulse for free")).toBeInTheDocument();
    // Readers can subscribe from the article itself — the analytics panel has
    // always said sign-ups come from here, and before this there was no form.
    expect(screen.getByText("Get the next My Project update by email")).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toBeInTheDocument();
  });

  it("attributes a sign-up to the article it was made on", async () => {
    api.publicArticle.mockResolvedValue({
      title: "Test Article",
      slug: "test-article",
      body_markdown: "Hello world",
      excerpt: "",
      meta_description: "",
      tags: [],
      word_count: 100,
      read_minutes: 1,
      project_name: "My Project",
      published_at: "2026-10-01T00:00:00",
    });
    api.subscribe.mockResolvedValue({ ok: true });
    wrap();
    fireEvent.change(await screen.findByLabelText("Email address"), {
      target: { value: "reader@example.com" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Subscribe" }));
    });
    expect(api.subscribe).toHaveBeenCalledWith("reader@example.com", "article", "test-article");
  });

  it("shows error state for missing article", async () => {
    api.publicArticle.mockRejectedValue(
      Object.assign(new Error("Not found"), { status: 404 }),
    );
    wrap("nonexistent");
    expect(
      await screen.findByText(/this article isn't available/i),
    ).toBeInTheDocument();
  });

  it("offers a retry, not 'unpublished', when the load itself failed", async () => {
    api.publicArticle.mockRejectedValue(new TypeError("Failed to fetch"));
    wrap("flaky");
    expect(await screen.findByText(/couldn't be loaded/)).toBeInTheDocument();
    expect(screen.queryByText(/removed or unpublished/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows Published with DoAide Pulse branding", async () => {
    api.publicArticle.mockResolvedValue({
      title: "Branded Article",
      slug: "branded-article",
      body_markdown: "Content",
      excerpt: "",
      tags: [],
      word_count: 50,
      read_minutes: 1,
    });
    wrap("branded-article");
    expect(
      await screen.findByText("Published with DoAide Pulse"),
    ).toBeInTheDocument();
  });
});

describe("PublicArticle's main landmark", () => {
  it.each([
    ["while the article is still loading", () => new Promise(() => {})],
    ["when the article is not found", () => Promise.reject(Object.assign(new Error("Not found"), { status: 404 }))],
    ["when the request fails", () => Promise.reject(Object.assign(new Error("down"), { status: 503 }))],
  ])("is there for the skip link %s", async (_state, answer) => {
    api.publicArticle.mockImplementation(answer);
    wrap("my-post");
    await act(async () => {});

    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute(
      "href",
      "#main",
    );
  });
});
