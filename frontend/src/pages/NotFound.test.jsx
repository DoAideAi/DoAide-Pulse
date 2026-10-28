import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import NotFound from "./NotFound";
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
