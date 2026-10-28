import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Unsubscribe from "./Unsubscribe";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({ api: { unsubscribe: vi.fn() } }));
vi.mock("../components/PublicNav", () => ({ default: () => null }));

function draw() {
  render(
    <MemoryRouter>
      <Unsubscribe />
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("Unsubscribe", () => {
  it("deletes the address and says it is off the list", async () => {
    api.unsubscribe.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    draw();
    await user.type(screen.getByLabelText("Email"), "  reader@example.com ");
    await user.click(screen.getByRole("button", { name: "Unsubscribe" }));

    expect(api.unsubscribe).toHaveBeenCalledWith("reader@example.com");
    expect(await screen.findByRole("status")).toHaveTextContent(
      "reader@example.com is not on the list any more.",
    );
  });

  it("will not send an empty address", () => {
    draw();
    expect(screen.getByRole("button", { name: "Unsubscribe" })).toBeDisabled();
  });

  it("explains a refused address in words", async () => {
    api.unsubscribe.mockRejectedValue(Object.assign(new Error("value is not a valid email"), { status: 422 }));
    const user = userEvent.setup();
    draw();
    await user.type(screen.getByLabelText("Email"), "x@y");
    await user.click(screen.getByRole("button", { name: "Unsubscribe" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That does not look like an email address.");
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });

  it("asks for patience when rate limited", async () => {
    api.unsubscribe.mockRejectedValue(Object.assign(new Error("Too many requests"), { status: 429 }));
    const user = userEvent.setup();
    draw();
    await user.type(screen.getByLabelText("Email"), "reader@example.com");
    await user.click(screen.getByRole("button", { name: "Unsubscribe" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("wait a minute");
  });
});
