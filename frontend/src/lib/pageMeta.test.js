import { afterEach, describe, expect, it } from "vitest";
import { applyPageMeta, canonicalUrl } from "./pageMeta";

function meta(selector) {
  return document.head.querySelector(selector)?.getAttribute("content");
}

describe("canonicalUrl", () => {
  it("keeps the root slash and drops trailing ones elsewhere", () => {
    expect(canonicalUrl("/")).toBe("https://pulse.doaide.com/");
    expect(canonicalUrl("/blog/")).toBe("https://pulse.doaide.com/blog");
    expect(canonicalUrl("tools/x")).toBe("https://pulse.doaide.com/tools/x");
  });
});

describe("applyPageMeta", () => {
  afterEach(() => {
    document.head.innerHTML = "";
  });

  it("creates missing tags", () => {
    applyPageMeta({ title: "T", description: "D", path: "/blog" });
    expect(document.title).toBe("T");
    expect(meta('meta[name="description"]')).toBe("D");
    expect(meta('meta[property="og:title"]')).toBe("T");
    expect(meta('meta[property="og:description"]')).toBe("D");
    expect(meta('meta[name="twitter:description"]')).toBe("D");
    expect(meta('meta[property="og:url"]')).toBe("https://pulse.doaide.com/blog");
    expect(
      document.head.querySelector('link[rel="canonical"]').getAttribute("href"),
    ).toBe("https://pulse.doaide.com/blog");
  });

  it("rewrites the homepage canonical instead of adding a second one", () => {
    document.head.innerHTML = '<link rel="canonical" href="https://pulse.doaide.com">';
    applyPageMeta({ path: "/templates" });
    const links = document.head.querySelectorAll('link[rel="canonical"]');
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("https://pulse.doaide.com/templates");
  });

  it("leaves a field alone when it is not given", () => {
    document.title = "Before";
    applyPageMeta({ description: "Only this" });
    expect(document.title).toBe("Before");
    expect(document.head.querySelector('link[rel="canonical"]')).toBeNull();
  });
});
