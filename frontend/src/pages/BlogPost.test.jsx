import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import BlogPost from "./BlogPost";

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/blog/:slug" element={<BlogPost />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("BlogPost", () => {
  it("renders article content by slug", async () => {
    renderAt("/blog/ai-newsletters-3x-engagement");
    expect(
      screen.getByRole("heading", { name: /AI-Powered Newsletters/ }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/newsletter landscape has shifted/)).toBeInTheDocument();
  });

  it("renders subject lines article", async () => {
    renderAt("/blog/subject-lines-40-percent-open-rates");
    expect(
      screen.getByRole("heading", { name: /40%\+ Open Rates/ }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/festival hook is the most powerful/)).toBeInTheDocument();
  });

  it("renders Indian creator playbook article", async () => {
    renderAt("/blog/newsletter-0-to-10000-indian-creator-playbook");
    expect(
      screen.getByRole("heading", { name: /0 to 10,000 Subscribers/ }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Indian creator economy is booming/)).toBeInTheDocument();
  });

  it("renders deliverability guide article", async () => {
    renderAt("/blog/email-deliverability-guide-avoid-spam-2026");
    expect(
      screen.getByRole("heading", { name: /Avoid the Spam Folder/ }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/DNS authentication is now mandatory/)).toBeInTheDocument();
  });

  it("shows 404 for unknown slug", () => {
    renderAt("/blog/nonexistent-post");
    expect(screen.getByText(/post not found/i)).toBeInTheDocument();
  });

  it("draws the heading at once and the body when it arrives", async () => {
    renderAt("/blog/ai-newsletters-3x-engagement");
    // Heading from the index, synchronously; body still loading.
    expect(screen.getByRole("heading", { name: /AI-Powered Newsletters/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Loading the post")).toBeInTheDocument();
    expect(await screen.findByText(/newsletter landscape has shifted/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Loading the post")).not.toBeInTheDocument();
  });

  it("does not bundle every post's text into the page", () => {
    // The page used to import data/blogPosts, which holds all of them: about
    // 125 KB downloaded to read one. It loads ../data/posts/<slug>.js instead.
    const source = readFileSync(resolve(__dirname, "BlogPost.jsx"), "utf8");
    expect(source).not.toMatch(/from "\.\.\/data\/blogPosts"/);
    expect(source).toContain('import.meta.glob("../data/posts/*.js")');
  });
});
