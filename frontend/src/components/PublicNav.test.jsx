import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import PublicNav from "./PublicNav";

const wrap = () =>
  render(
    <MemoryRouter>
      <PublicNav />
    </MemoryRouter>,
  );

describe("PublicNav tools disclosure", () => {
  it("stays open while Tab moves into it", async () => {
    wrap();
    const button = screen.getByRole("button", { name: /free tools/i });
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");

    await userEvent.tab();
    const first = screen.getByRole("link", { name: "Subject Line Tester" });
    expect(first).toHaveFocus();
    // Closing on the button's blur unmounted the link focus had just reached.
    await new Promise((r) => setTimeout(r, 200));
    expect(screen.getByRole("link", { name: "Subject Line Tester" })).toBeInTheDocument();
  });

  it("closes on Escape from inside and returns focus to the button", async () => {
    wrap();
    const button = screen.getByRole("button", { name: /free tools/i });
    await userEvent.click(button);
    await userEvent.tab();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("link", { name: "Subject Line Tester" })).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("closes once focus leaves the group", async () => {
    wrap();
    await userEvent.click(screen.getByRole("button", { name: /free tools/i }));
    for (let i = 0; i < 5; i += 1) await userEvent.tab();
    expect(screen.queryByRole("link", { name: "Subject Line Tester" })).not.toBeInTheDocument();
  });
});
