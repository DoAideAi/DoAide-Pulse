import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SubscribeForm from "./SubscribeForm";

vi.mock("../lib/api", () => ({ api: { subscribe: vi.fn() } }));
vi.mock("../lib/trackEvent", () => ({ default: vi.fn() }));

import { api } from "../lib/api";

describe("SubscribeForm", () => {
  beforeEach(() => vi.clearAllMocks());

  it("passes the article it sits on, so the sign-up is attributed to its project", async () => {
    api.subscribe.mockResolvedValue({ ok: true });
    render(<SubscribeForm source="article" article="pulse-2-0" />);
    await userEvent.type(screen.getByLabelText("Email address"), "reader@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Subscribe" }));
    expect(api.subscribe).toHaveBeenCalledWith("reader@example.com", "article", "pulse-2-0");
  });

  it("subscribes with the page's source tag and confirms", async () => {
    api.subscribe.mockResolvedValue({ ok: true });
    render(<SubscribeForm source="article" />);
    await userEvent.type(screen.getByLabelText("Email address"), " reader@example.com ");
    await userEvent.click(screen.getByRole("button", { name: "Subscribe" }));
    expect(api.subscribe).toHaveBeenCalledWith("reader@example.com", "article", undefined);
    expect(await screen.findByRole("status")).toHaveTextContent("You're subscribed");
    // Leaving is offered as soon as joining is done.
    expect(screen.getByRole("link", { name: "Unsubscribe" })).toHaveAttribute("href", "/unsubscribe");
    expect(screen.queryByRole("button", { name: "Subscribe" })).not.toBeInTheDocument();
  });

  it("keeps the form and focuses the field when the address is refused", async () => {
    api.subscribe.mockRejectedValue(Object.assign(new Error("bad"), { status: 422 }));
    render(<SubscribeForm />);
    const input = screen.getByLabelText("Email address");
    await userEvent.type(input, "not-an-email");
    await userEvent.click(screen.getByRole("button", { name: "Subscribe" }));
    expect(await screen.findByText("That doesn't look like an email address.")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveFocus();
    expect(input).toHaveValue("not-an-email");
  });

  it("explains a rate limit rather than a generic failure", async () => {
    api.subscribe.mockRejectedValue(Object.assign(new Error("slow"), { status: 429 }));
    render(<SubscribeForm />);
    await userEvent.type(screen.getByLabelText("Email address"), "a@b.co");
    await userEvent.click(screen.getByRole("button", { name: "Subscribe" }));
    expect(await screen.findByText(/Too many attempts/)).toBeInTheDocument();
  });

  it("asks for an address instead of posting an empty one", async () => {
    render(<SubscribeForm />);
    await userEvent.click(screen.getByRole("button", { name: "Subscribe" }));
    expect(api.subscribe).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Enter your email address.");
  });
});
