import { describe, expect, it } from "vitest";
import { indexedLabel, sitemapState, sortSites, toneClass } from "./seo";

function site(overrides = {}) {
  return {
    key: "gst",
    name: "GST",
    checked: true,
    fetch_error: null,
    submit_status: "submitted",
    submit_error: null,
    gsc_submitted: 40,
    gsc_indexed: 31,
    gsc_errors: 0,
    ...overrides,
  };
}

describe("sitemapState", () => {
  it("names the worst thing first", () => {
    expect(sitemapState(site({ checked: false })).label).toBe("Not checked yet");
    expect(sitemapState(site({ fetch_error: "404", submit_status: "error" })).label).toBe(
      "Sitemap unreachable",
    );
    expect(sitemapState(site({ submit_status: "error" })).tone).toBe("bad");
    expect(sitemapState(site({ submit_status: "unconfigured" })).tone).toBe("warn");
    expect(sitemapState(site({ gsc_errors: 2 })).label).toBe("2 Google errors");
    expect(sitemapState(site())).toEqual({ tone: "good", label: "Submitted" });
  });

  it("maps every tone to classes", () => {
    expect(toneClass("good")).toContain("text-good");
    expect(toneClass("bad")).toContain("text-bad");
    expect(toneClass("other")).toBe("text-ink-400");
  });
});

describe("indexedLabel", () => {
  it("does not read Google's missing count as zero", () => {
    expect(indexedLabel(site({ gsc_indexed: 0 }))).toBe("not reported");
    expect(indexedLabel(site({ gsc_indexed: null }))).toBe("—");
    expect(indexedLabel(site())).toBe("31");
  });
});

describe("sortSites", () => {
  it("puts problems first, then sorts by name", () => {
    const sorted = sortSites([
      site({ key: "a", name: "Zeta" }),
      site({ key: "b", name: "Alpha" }),
      site({ key: "c", name: "Mid", fetch_error: "404" }),
      site({ key: "d", name: "Beta", checked: false }),
    ]);
    expect(sorted.map((s) => s.key)).toEqual(["c", "d", "b", "a"]);
  });
});
