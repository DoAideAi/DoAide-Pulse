import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminFeedback from "./AdminFeedback";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({
  api: { listFeedback: vi.fn(), feedbackFeatures: vi.fn() },
}));

const ROW = {
  id: 1,
  category: "bug",
  message: "The calendar loses a post.",
  email: "reader@example.com",
  page_url: "/calendar",
  detected_feature: "Calendar",
  user_agent: "Mozilla/5.0 TestBrowser",
  created_at: "2026-10-28T10:00:00+00:00",
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listFeedback.mockResolvedValue([ROW]);
  api.feedbackFeatures.mockResolvedValue(["Analytics", "Calendar"]);
});

describe("AdminFeedback", () => {
  it("lists each piece with its category, feature, page, email and browser", async () => {
    render(<AdminFeedback />);
    const item = within(await screen.findByRole("list", { name: "Feedback" })).getByRole("listitem");
    expect(item).toHaveTextContent("Bug Report");
    expect(item).toHaveTextContent("Calendar");
    expect(item).toHaveTextContent("The calendar loses a post.");
    expect(item).toHaveTextContent("/calendar");
    expect(within(item).getByRole("link", { name: "reader@example.com" })).toHaveAttribute(
      "href",
      "mailto:reader@example.com",
    );
    expect(item).toHaveTextContent("Mozilla/5.0 TestBrowser");
  });

  it("filters by category and by the feature areas feedback has named", async () => {
    const user = userEvent.setup();
    render(<AdminFeedback />);
    await screen.findByRole("list", { name: "Feedback" });

    await user.selectOptions(screen.getByLabelText("Category"), "bug");
    expect(api.listFeedback).toHaveBeenLastCalledWith(
      expect.objectContaining({ category: "bug", feature: "" }),
    );
    await user.selectOptions(await screen.findByLabelText("Feature"), "Calendar");
    expect(api.listFeedback).toHaveBeenLastCalledWith(
      expect.objectContaining({ category: "bug", feature: "Calendar" }),
    );
  });

  it("filters by date range", async () => {
    const user = userEvent.setup();
    render(<AdminFeedback />);
    await screen.findByRole("list", { name: "Feedback" });
    await user.type(screen.getByLabelText("From"), "2026-10-01");
    expect(api.listFeedback).toHaveBeenLastCalledWith(
      expect.objectContaining({ since: "2026-10-01" }),
    );
  });

  it("says no feedback matches, rather than none exists, when filtered", async () => {
    const user = userEvent.setup();
    render(<AdminFeedback />);
    await screen.findByRole("list", { name: "Feedback" });
    api.listFeedback.mockResolvedValue([]);
    await user.selectOptions(screen.getByLabelText("Category"), "feature");
    expect(await screen.findByText("No feedback matches these filters")).toBeInTheDocument();
  });

  it("tells a non-operator they cannot read it, instead of showing an empty list", async () => {
    const refused = Object.assign(new Error("Feedback is readable by this install's operator only."), {
      status: 403,
    });
    api.listFeedback.mockRejectedValue(refused);
    api.feedbackFeatures.mockRejectedValue(refused);
    render(<AdminFeedback />);
    expect(await screen.findByText(/operator only/)).toBeInTheDocument();
    expect(screen.queryByText("No feedback yet")).not.toBeInTheDocument();
  });
});
