import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const SOURCE = readFileSync(resolve(__dirname, "../../public/embed.js"), "utf8");

function run() {
  // eslint-disable-next-line no-new-func
  new Function(SOURCE)();
}

describe("public/embed.js", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    delete window.__pulseEmbed;
  });
  afterEach(() => vi.restoreAllMocks());

  it("labels the email field and announces the outcome", () => {
    document.body.innerHTML = '<div data-pulse-signup data-name="Weekly"></div>';
    run();
    const input = document.querySelector("input[type=email]");
    expect(input.getAttribute("aria-label")).toBe("Email address");
    expect(document.querySelector("[role=status]").getAttribute("aria-live")).toBe("polite");
  });

  it("does not render a second form when the script loads twice", () => {
    document.body.innerHTML = "<div data-pulse-signup></div>";
    run();
    run();
    expect(document.querySelectorAll("form")).toHaveLength(1);
  });

  it("refuses a colour that is not hex instead of writing it into markup", () => {
    document.body.innerHTML =
      '<div data-pulse-signup data-color="red;&quot;&gt;&lt;img src=x onerror=alert(1)&gt;"></div>';
    run();
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("a").style.color).toBe("rgb(240, 180, 41)");
  });

  it("expands a short hex and picks readable button text", () => {
    run();
    const { hexColor, textOn } = window.__pulseEmbed;
    expect(hexColor("#abc")).toBe("#AABBCC");
    expect(hexColor("0d9488")).toBe("#0D9488");
    expect(textOn("#1E3A8A")).toBe("#FFFFFF");
    expect(textOn("#F0B429")).toBe("#0A0A0B");
  });

  it("waits for the document when it runs before the container is parsed", () => {
    Object.defineProperty(document, "readyState", { value: "loading", configurable: true });
    run();
    document.body.innerHTML = "<div data-pulse-signup></div>";
    expect(document.querySelector("form")).toBeNull();
    delete document.readyState;
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(document.querySelector("form")).not.toBeNull();
  });
});
