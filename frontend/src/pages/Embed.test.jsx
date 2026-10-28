import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Embed, { embedCode, normalizeHex, textOn } from "./Embed";
import { ROUTER_FUTURE } from "../lib/routerFuture";

function renderPage() {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <Embed />
    </MemoryRouter>,
  );
}

const code = () => screen.getByLabelText("Embed code").value;

describe("Embed generator", () => {
  afterEach(() => vi.restoreAllMocks());

  it("escapes a name that would otherwise break the pasted snippet", () => {
    renderPage();
    fireEvent.change(screen.getByLabelText("Newsletter name"), {
      target: { value: 'Tom\'s "Weekly" <b>' },
    });
    expect(code()).toContain('data-name="Tom\'s &quot;Weekly&quot; &lt;b&gt;"');
  });

  it("keeps the last valid colour while the hex box holds a half-typed one", () => {
    renderPage();
    const hex = screen.getByLabelText("Color hex");
    fireEvent.change(hex, { target: { value: "#12" } });
    expect(hex).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/Use a hex colour/)).toBeInTheDocument();
    expect(code()).toContain('data-color="#0D9488"');

    fireEvent.change(hex, { target: { value: "#1e3a8a" } });
    expect(hex).toHaveAttribute("aria-invalid", "false");
    expect(code()).toContain('data-color="#1E3A8A"');
    expect(screen.getByRole("button", { name: "Subscribe" })).toHaveStyle({ color: "#FFFFFF" });
  });

  it("copies the snippet and says so", async () => {
    const writeText = vi.fn().mockResolvedValue();
    Object.assign(navigator, { clipboard: { writeText } });
    renderPage();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy code" })));
    expect(writeText).toHaveBeenCalledWith(code());
    expect(screen.getByRole("status")).toHaveTextContent(/Copied to the clipboard/);
  });

  it("explains a refused clipboard instead of doing nothing", async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("no")) } });
    renderPage();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy code" })));
    expect(screen.getByRole("status")).toHaveTextContent(/blocked clipboard access/);
  });

  it("builds the snippet the widget reads", () => {
    expect(
      embedCode({ origin: "https://x.test", name: " ", color: "#ABCDEF", layout: "full", source: "footer" }),
    ).toBe(
      '<div data-pulse-signup data-name="Newsletter" data-color="#ABCDEF" data-layout="full" data-source="footer"></div>\n<script src="https://x.test/embed.js" async></script>',
    );
    expect(normalizeHex("abc")).toBe("#AABBCC");
    expect(normalizeHex("#12")).toBeNull();
    expect(textOn("#F0B429")).toBe("#0A0A0B");
  });
});
