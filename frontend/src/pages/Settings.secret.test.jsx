import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OneTimeSecret } from "./Settings";

vi.mock("../lib/api", () => ({ api: {} }));

describe("OneTimeSecret", () => {
  afterEach(() => vi.restoreAllMocks());

  it("labels the value and copies it", async () => {
    const writeText = vi.fn().mockResolvedValue();
    Object.assign(navigator, { clipboard: { writeText } });
    render(<OneTimeSecret title="API token" value="pulse_abc" onClose={() => {}} />);
    expect(screen.getByRole("textbox", { name: "API token" })).toHaveValue("pulse_abc");
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy" })));
    expect(writeText).toHaveBeenCalledWith("pulse_abc");
    expect(screen.getByRole("status")).toHaveTextContent("Copied to the clipboard.");
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
  });

  it("is not lost to a stray Escape before it has been copied", async () => {
    const onClose = vi.fn();
    render(<OneTimeSecret title="Signing secret" value="whsec_1" onClose={onClose} />);
    fireEvent.keyDown(document.activeElement || document.body, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "I've saved it" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape once copied", async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue() } });
    const onClose = vi.fn();
    render(<OneTimeSecret title="API token" value="t" onClose={onClose} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy" })));
    fireEvent.keyDown(document.activeElement, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("explains a refused clipboard", async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("x")) } });
    render(<OneTimeSecret title="API token" value="t" onClose={() => {}} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy" })));
    expect(screen.getByRole("status")).toHaveTextContent(/blocked clipboard access/);
  });
});
