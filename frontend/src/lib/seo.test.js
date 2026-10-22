import { describe, expect, it } from "vitest";
import {
  indexedLabel,
  insertLink,
  metaLengthHint,
  parseKeywords,
  postLabel,
  postTone,
  sitemapState,
  sortSites,
  toneClass,
} from "./seo";

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

describe("metaLengthHint", () => {
  it("steers toward Google's visible length", () => {
    expect(metaLengthHint("").tone).toBe("idle");
    expect(metaLengthHint("x".repeat(50)).tone).toBe("warn");
    expect(metaLengthHint("x".repeat(140))).toEqual({ tone: "good", hint: "140 characters — good length." });
    expect(metaLengthHint("x".repeat(200)).hint).toMatch(/cut it off/);
  });
});

describe("parseKeywords", () => {
  it("splits, trims and deduplicates without caring about case", () => {
    expect(parseKeywords("gst, Input tax credit ,, itr, GST")).toEqual([
      "gst",
      "Input tax credit",
      "itr",
    ]);
    expect(parseKeywords("")).toEqual([]);
  });
});

describe("insertLink", () => {
  const url = "https://tax.doaide.com/";

  it("links the first plain mention, keeping its case", () => {
    const body = "# Income tax basics\n\nFiling Income Tax is easy. Income tax again.";
    expect(insertLink(body, "income tax", url)).toBe(
      `# Income tax basics\n\nFiling [Income Tax](${url}) is easy. Income tax again.`,
    );
  });

  it("does not link inside an existing link or a longer word", () => {
    const body = "See [income tax rules](https://x.test). Taxes and ITRs.";
    expect(insertLink(body, "income tax", url)).toBe(`${body}\n\nRelated: [income tax](${url})\n`);
    expect(insertLink("ITRs everywhere", "itr", url)).toMatch(/Related: \[itr\]/);
  });

  it("starts an empty body with the link", () => {
    expect(insertLink("", "gst", "https://gst.doaide.com/")).toBe(
      "Related: [gst](https://gst.doaide.com/)\n",
    );
  });
});

describe("post status", () => {
  it("reads the furthest stage reached", () => {
    expect(postLabel({ status: "approved", scheduled_for: "2026-10-30T00:00:00Z" })).toBe("Scheduled");
    expect(postTone({ status: "approved", scheduled_for: "x" })).toBe("warn");
    expect(postLabel({ status: "published", published_at: "x" })).toBe("Published");
    expect(postLabel({ status: "draft" })).toBe("Draft");
    expect(postLabel({ status: "review" })).toBe("Review");
    expect(postTone({ status: "failed" })).toBe("bad");
  });
});
