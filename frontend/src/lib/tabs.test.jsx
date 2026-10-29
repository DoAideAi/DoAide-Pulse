import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { onTabListKeyDown, tabProps } from "./tabs";

function Tabs({ names = ["One", "Two", "Three"] }) {
  const [active, setActive] = useState(names[0]);
  return (
    <div role="tablist" aria-label="Demo" onKeyDown={onTabListKeyDown}>
      {names.map((name) => (
        <button key={name} type="button" role="tab" {...tabProps(name === active)} onClick={() => setActive(name)}>
          {name}
        </button>
      ))}
    </div>
  );
}

const tab = (name) => screen.getByRole("tab", { name });

describe("a tab list", () => {
  it("is one stop in the Tab order: the selected tab", () => {
    render(<Tabs />);
    expect(tab("One")).toHaveAttribute("tabindex", "0");
    expect(tab("Two")).toHaveAttribute("tabindex", "-1");
    expect(tab("Three")).toHaveAttribute("tabindex", "-1");
  });

  it("moves and selects with the arrow keys, wrapping at the ends", () => {
    render(<Tabs />);
    tab("One").focus();

    fireEvent.keyDown(tab("One"), { key: "ArrowRight" });
    expect(tab("Two")).toHaveFocus();
    expect(tab("Two")).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(tab("Two"), { key: "ArrowLeft" });
    fireEvent.keyDown(tab("One"), { key: "ArrowLeft" });
    expect(tab("Three")).toHaveFocus();
    expect(tab("Three")).toHaveAttribute("aria-selected", "true");
    expect(tab("Three")).toHaveAttribute("tabindex", "0");
  });

  it("jumps with Home and End", () => {
    render(<Tabs />);
    tab("One").focus();
    fireEvent.keyDown(tab("One"), { key: "End" });
    expect(tab("Three")).toHaveFocus();
    fireEvent.keyDown(tab("Three"), { key: "Home" });
    expect(tab("One")).toHaveFocus();
  });

  it("leaves every other key alone", () => {
    render(<Tabs />);
    tab("One").focus();
    const event = fireEvent.keyDown(tab("One"), { key: "a" });
    expect(event).toBe(true);
    expect(tab("One")).toHaveFocus();
  });
});
