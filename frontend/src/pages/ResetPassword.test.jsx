import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import ResetPassword from "./ResetPassword";

vi.mock("../lib/api", () => ({
  api: { requestPasswordReset: vi.fn(), confirmPasswordReset: vi.fn() },
}));
vi.mock("../components/PublicNav", () => ({ default: () => null }));

const TOKEN = "Zk3_q-9aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789";

function open(url) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ResetPassword />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("asking for a link", () => {
  it("sends the address and answers without saying whether it has an account", async () => {
    api.requestPasswordReset.mockResolvedValue({ detail: "ok" });
    open("/reset-password");

    await userEvent.type(screen.getByLabelText("Email"), "ana@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Email me a link" }));

    expect(api.requestPasswordReset).toHaveBeenCalledWith("ana@example.com");
    expect(await screen.findByRole("status")).toHaveTextContent(
      "If ana@example.com has a Pulse account",
    );
  });

  it("announces a refusal", async () => {
    api.requestPasswordReset.mockRejectedValue(Object.assign(new Error("slow"), { status: 429 }));
    open("/reset-password");

    await userEvent.type(screen.getByLabelText("Email"), "ana@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Email me a link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });
});

describe("using the link from the email", () => {
  it("sets the new password with the token from the URL", async () => {
    api.confirmPasswordReset.mockResolvedValue({ detail: "ok" });
    open(`/reset-password?token=${TOKEN}`);

    await userEvent.type(screen.getByLabelText("New password"), "a-new-long-password");
    await userEvent.type(screen.getByLabelText("The same again"), "a-new-long-password");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));

    expect(api.confirmPasswordReset).toHaveBeenCalledWith(TOKEN, "a-new-long-password");
    expect(await screen.findByRole("status")).toHaveTextContent("Your password has been changed");
    expect(screen.getByRole("link", { name: "Sign in with the new one" })).toHaveAttribute("href", "/");
  });

  it("takes the token out of the address bar once it has read it", () => {
    window.history.replaceState(null, "", `/reset-password?token=${TOKEN}`);
    open(`/reset-password?token=${TOKEN}`);

    expect(window.location.search).toBe("");
    expect(window.location.href).not.toContain(TOKEN);
    expect(screen.getByLabelText("New password")).toBeInTheDocument();
  });

  it("refuses two different passwords without asking the server", async () => {
    open(`/reset-password?token=${TOKEN}`);

    await userEvent.type(screen.getByLabelText("New password"), "a-new-long-password");
    await userEvent.type(screen.getByLabelText("The same again"), "a-different-password");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));

    expect(api.confirmPasswordReset).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("not the same");
  });

  it("offers a new link when this one is spent", async () => {
    api.confirmPasswordReset.mockRejectedValue(
      Object.assign(
        new Error("This reset link is invalid, already used, or expired. Request a new one."),
        { status: 400 },
      ),
    );
    open(`/reset-password?token=${TOKEN}`);

    await userEvent.type(screen.getByLabelText("New password"), "a-new-long-password");
    await userEvent.type(screen.getByLabelText("The same again"), "a-new-long-password");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already used, or expired");
    expect(screen.getByRole("link", { name: "Ask for a new link." })).toHaveAttribute(
      "href",
      "/reset-password",
    );
  });
});
