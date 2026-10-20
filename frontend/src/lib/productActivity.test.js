import { describe, expect, it } from "vitest";
import {
  averageVisitSeconds,
  bounceRate,
  formatSeconds,
  sortProducts,
  umamiNotice,
} from "./productActivity";

describe("bounceRate", () => {
  it("divides bounces by visits", () => {
    expect(bounceRate({ visits: 10, bounces: 4 })).toBe(0.4);
  });
  it("is unknown with no visits, not zero", () => {
    expect(bounceRate({ visits: 0, bounces: 0 })).toBeNull();
    expect(bounceRate(undefined)).toBeNull();
  });
  it("never exceeds one", () => {
    expect(bounceRate({ visits: 2, bounces: 3 })).toBe(1);
  });
});

describe("averageVisitSeconds / formatSeconds", () => {
  it("averages total time over visits", () => {
    expect(averageVisitSeconds({ visits: 4, totaltime: 610 })).toBe(153);
    expect(averageVisitSeconds({ visits: 0, totaltime: 5 })).toBeNull();
  });
  it("formats seconds and minutes", () => {
    expect(formatSeconds(42)).toBe("42s");
    expect(formatSeconds(185)).toBe("3m 05s");
    expect(formatSeconds(null)).toBe("—");
  });
});

describe("umamiNotice", () => {
  it("is silent when the numbers are there", () => {
    expect(umamiNotice({ status: "ok" })).toBeNull();
  });
  it("names each failure", () => {
    expect(umamiNotice({ status: "unconfigured" })).toMatch(/not configured/);
    expect(umamiNotice({ status: "not_found" })).toMatch(/No Umami site/);
    expect(umamiNotice({ status: "error", error: "Umami login refused (403)" })).toBe(
      "Umami error: Umami login refused (403)",
    );
  });
});

describe("sortProducts", () => {
  const p = (key, status, active_now, pageviews) => ({
    key,
    umami: { status, active_now, pageviews },
  });

  it("puts live products first, then by active visitors and page views", () => {
    const sorted = sortProducts([
      p("a", "error", 0, 0),
      p("b", "ok", 0, 50),
      p("c", "ok", 3, 10),
      p("d", "ok", 0, 90),
      p("e", "not_found", 0, 0),
    ]);
    expect(sorted.map((x) => x.key)).toEqual(["c", "d", "b", "a", "e"]);
  });

  it("does not mutate its input", () => {
    const input = [p("a", "ok", 0, 1), p("b", "ok", 5, 1)];
    sortProducts(input);
    expect(input.map((x) => x.key)).toEqual(["a", "b"]);
  });
});
