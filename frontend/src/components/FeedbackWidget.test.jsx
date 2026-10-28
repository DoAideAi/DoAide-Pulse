import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FeedbackWidget from "./FeedbackWidget";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({ api: { submitFeedback: vi.fn() } }));

function draw(path = "/content/42") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <FeedbackWidget />
    </MemoryRouter>,
  );
}

async function openForm(user) {
  await user.click(screen.getByRole("button", { name: "Feedback" }));
  return screen.getByRole("dialog", { name: "Send feedback" });
}

beforeEach(() => {
  vi.clearAllMocks();
  api.submitFeedback.mockResolvedValue({ id: 1, ok: true });
});

describe("FeedbackWidget", () => {
  it("is a blue floating button", () => {
    draw();
    expect(screen.getByRole("button", { name: "Feedback" })).toHaveStyle({
      backgroundColor: "#2563eb",
    });
  });

  it("says which feature it detected, and lets the person change it", async () => {
    const user = userEvent.setup();
    draw("/content/42");
    await openForm(user);

    const about = screen.getByLabelText("Feedback about");
    expect(about).toHaveValue("Content Editor");
    await user.selectOptions(about, "Translations");
    expect(about).toHaveValue("Translations");
  });

  it("shows what is sent along with the message", async () => {
    const user = userEvent.setup();
    draw("/analytics");
    await openForm(user);
    expect(screen.getByLabelText("Feedback about")).toHaveValue("Analytics");
    expect(screen.getByText("/analytics")).toBeInTheDocument();
  });

  it("will not send without a message", async () => {
    const user = userEvent.setup();
    draw();
    await openForm(user);
    expect(screen.getByRole("button", { name: "Send feedback" })).toBeDisabled();
    await user.type(screen.getByLabelText("Your feedback"), "   ");
    expect(screen.getByRole("button", { name: "Send feedback" })).toBeDisabled();
    expect(api.submitFeedback).not.toHaveBeenCalled();
  });

  it("sends the category, message, optional email and the context", async () => {
    const user = userEvent.setup();
    draw("/calendar");
    await openForm(user);
    await user.selectOptions(screen.getByLabelText("Category"), "bug");
    await user.type(screen.getByLabelText("Your feedback"), "  Dragging a post loses it.  ");
    await user.click(screen.getByRole("button", { name: "Send feedback" }));

    expect(api.submitFeedback).toHaveBeenCalledWith({
      category: "bug",
      message: "Dragging a post loses it.",
      email: null,
      page_url: "/calendar",
      detected_feature: "Calendar",
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Your feedback about Calendar has been sent.",
    );
  });

  it("passes an email along when one is given", async () => {
    const user = userEvent.setup();
    draw();
    await openForm(user);
    await user.type(screen.getByLabelText("Your feedback"), "Hi");
    await user.type(screen.getByLabelText(/^Email/), "me@example.com");
    await user.click(screen.getByRole("button", { name: "Send feedback" }));
    expect(api.submitFeedback.mock.calls[0][0].email).toBe("me@example.com");
  });

  it("explains the hourly limit instead of quoting a status", async () => {
    api.submitFeedback.mockRejectedValue(Object.assign(new Error("Too many requests"), { status: 429 }));
    const user = userEvent.setup();
    draw();
    await openForm(user);
    await user.type(screen.getByLabelText("Your feedback"), "Again");
    await user.click(screen.getByRole("button", { name: "Send feedback" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("try again later");
    // The form stays open with what they wrote.
    expect(screen.getByLabelText("Your feedback")).toHaveValue("Again");
  });

  it("reports any other failure with the server's reason", async () => {
    api.submitFeedback.mockRejectedValue(Object.assign(new Error("Write something before sending."), { status: 422 }));
    const user = userEvent.setup();
    draw();
    await openForm(user);
    await user.type(screen.getByLabelText("Your feedback"), "x");
    await user.click(screen.getByRole("button", { name: "Send feedback" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not send your feedback: Write something before sending.",
    );
  });

  it.each(["/embed", "/preview/abc123"])("stays off %s, which is not Pulse's own UI", (path) => {
    draw(path);
    expect(screen.queryByRole("button", { name: "Feedback" })).not.toBeInTheDocument();
  });
});
