import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import NotFound, { displayPath } from "./NotFound";
import { useAuth } from "../hooks/useAuth";

vi.mock("../hooks/useAuth", () => ({ useAuth: vi.fn() }));

function draw(path, user) {
  useAuth.mockReturnValue({ user, loading: false });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <NotFound />
    </MemoryRouter>,
  );
}

describe("NotFound", () => {
  afterEach(() => {
    document.head.querySelectorAll('meta[name="robots"]').forEach((m) => m.remove());
  });

  it("says the page is not there and quotes the address", () => {
    draw("/blog/an-old-post", null);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/couldn.t find that page/i);
    expect(screen.getByText("/blog/an-old-post")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
  });

  it("sends a signed-out visitor home", () => {
    draw("/nope", null);
    expect(screen.getByRole("link", { name: "Go to the home page" })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("link", { name: /dashboard/i })).not.toBeInTheDocument();
  });

  it("offers a signed-in user their dashboard", () => {
    draw("/nope", { id: 1 });
    expect(screen.getByRole("link", { name: "Go to your dashboard" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
  });

  it("asks search engines not to index it, and tidies up after itself", () => {
    const { unmount } = draw("/nope", null);
    expect(document.title).toMatch(/page not found/i);
    expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute("content", "noindex");
    unmount();
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });
});

describe("NotFound with awkward addresses", () => {
  afterEach(() => {
    document.head.querySelectorAll('meta[name="robots"]').forEach((m) => m.remove());
  });

  it("shows an encoded address the way it was typed", () => {
    draw("/caf%C3%A9/%E2%9C%93", null);
    expect(screen.getByText("/café/✓")).toBeInTheDocument();
  });

  it("survives a malformed escape and shows it as it came", () => {
    expect(displayPath("/bad%E0%A4%A")).toBe("/bad%E0%A4%A");
    draw("/bad%E0%A4%A", null);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByText("/bad%E0%A4%A")).toBeInTheDocument();
  });

  it("quotes the path only — not the query or the fragment", () => {
    draw("/old-post?utm_source=mail&token=abc#section-2", null);
    expect(screen.getByText("/old-post")).toBeInTheDocument();
    expect(screen.queryByText(/token=abc/)).not.toBeInTheDocument();
    expect(screen.queryByText(/section-2/)).not.toBeInTheDocument();
  });

  it("renders markup in the address as text, never as markup", () => {
    const { container } = draw("/%3Cimg%20src=x%20onerror=alert(1)%3E", null);
    expect(screen.getByText("/<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("keeps a very long address from widening the page", () => {
    draw(`/${"a".repeat(2000)}`, null);
    expect(screen.getByText(`/${"a".repeat(2000)}`)).toHaveClass("break-all");
  });
});

