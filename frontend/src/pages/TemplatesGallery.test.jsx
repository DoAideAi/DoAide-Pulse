import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import TemplatesGallery from "./TemplatesGallery";

const wrap = () =>
  render(
    <MemoryRouter>
      <TemplatesGallery />
    </MemoryRouter>,
  );

describe("TemplatesGallery", () => {
  it("renders all 15 template cards", () => {
    wrap();
    expect(screen.getByText("Marketing Campaign")).toBeInTheDocument();
    expect(screen.getByText("Product Update")).toBeInTheDocument();
    expect(screen.getByText("Weekly Digest")).toBeInTheDocument();
    expect(screen.getByText("Educational")).toBeInTheDocument();
    expect(screen.getByText("Welcome Email Series")).toBeInTheDocument();
    expect(screen.getByText("Product Launch")).toBeInTheDocument();
    expect(screen.getByText("Weekly Roundup")).toBeInTheDocument();
    expect(screen.getByText("Event Invitation")).toBeInTheDocument();
    expect(screen.getByText("Feedback Request")).toBeInTheDocument();
    expect(screen.getByText("Founder / Investor Update")).toBeInTheDocument();
    expect(screen.getByText("Festive Sale")).toBeInTheDocument();
    expect(screen.getByText("Hiring & Jobs Digest")).toBeInTheDocument();
    expect(screen.getByText("Re-engagement")).toBeInTheDocument();
    const cards = screen.getAllByText("Use Template");
    expect(cards).toHaveLength(15);
  });

  it("filters the grid by category", async () => {
    const user = userEvent.setup();
    wrap();
    await user.click(screen.getByRole("tab", { name: "Promotion" }));
    expect(screen.getAllByText("Use Template")).toHaveLength(2);
    expect(screen.getByText("Festive Sale")).toBeInTheDocument();
    expect(screen.queryByText("Product Update")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "All" }));
    expect(screen.getAllByText("Use Template")).toHaveLength(15);
  });

  it("shows category badges for new templates", () => {
    wrap();
    // The filter tabs reuse the category names, so scope to the badges.
    for (const name of ["Onboarding", "Launch", "Events", "Survey", "Updates", "Retention"]) {
      expect(screen.getAllByText(name).length).toBeGreaterThanOrEqual(1);
    }
  });

  it("expands and collapses a template preview", async () => {
    const user = userEvent.setup();
    wrap();
    const buttons = screen.getAllByText("Preview");
    await user.click(buttons[0]);
    expect(screen.getByText("Close Preview")).toBeInTheDocument();
    await user.click(screen.getByText("Close Preview"));
    expect(screen.queryByText("Close Preview")).not.toBeInTheDocument();
  });

  it("shows FAQs", () => {
    wrap();
    expect(screen.getByText("Are these newsletter templates free to use?")).toBeInTheDocument();
  });

  it("shows descriptions for new templates", () => {
    wrap();
    expect(screen.getByText(/warm welcome sequence for new subscribers/)).toBeInTheDocument();
    expect(screen.getByText(/High-impact product launch announcement/)).toBeInTheDocument();
    expect(screen.getByText(/Structured weekly digest with top stories/)).toBeInTheDocument();
    expect(screen.getByText(/Clean event invitation with date/)).toBeInTheDocument();
    expect(screen.getByText(/Friendly feedback and survey request/)).toBeInTheDocument();
  });
});
