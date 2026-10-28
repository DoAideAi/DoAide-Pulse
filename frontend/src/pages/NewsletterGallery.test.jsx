import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import NewsletterGallery from "./NewsletterGallery";
import { ROUTER_FUTURE } from "../lib/routerFuture";

function renderPage() {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <NewsletterGallery />
    </MemoryRouter>,
  );
}

describe("NewsletterGallery", () => {
  it("claims no open rates or timings for newsletters that are mockups", () => {
    renderPage();
    expect(screen.queryByText(/open rate/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Generated in/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument();
    expect(screen.getAllByText("Sample layout")).toHaveLength(6);
    const ld = [...document.head.querySelectorAll('script[type="application/ld+json"]')]
      .map((el) => el.textContent)
      .join("");
    expect(ld).not.toMatch(/open rates? of|\d+%/i);
  });

  it("expands one sample, names it, and points the button at what it opened", () => {
    renderPage();
    const toggle = screen.getByRole("button", { name: "Expand the Design Digest sample" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    const close = screen.getByRole("button", { name: "Close the Design Digest sample" });
    expect(close).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById(close.getAttribute("aria-controls"))).not.toBeNull();
    expect(screen.queryByText("Read Full Issue")?.closest('[aria-hidden="true"]')).not.toBeNull();
  });

  it("sends Create Similar to sign-up rather than back to the landing page", () => {
    renderPage();
    const link = screen.getByRole("link", { name: "Create a newsletter like The AI Weekly" });
    expect(link).toHaveAttribute("href", "/login");
  });
});
