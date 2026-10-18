import { describe, expect, it } from "vitest";
import { PLATFORM_GUIDES, groupPlatforms, guideFor } from "./platformGuides";

function p(platform, overrides = {}) {
  return { platform, display_name: platform, implemented: true, connection: null, ...overrides };
}

describe("guideFor", () => {
  it("returns the curated guide for a known platform", () => {
    expect(guideFor(p("devto"))).toBe(PLATFORM_GUIDES.devto);
  });

  it("falls back to a generic guide naming the platform", () => {
    const guide = guideFor(p("newsite", { display_name: "New Site" }));
    expect(guide.setupUrl).toBeNull();
    expect(guide.steps[0]).toContain("New Site");
  });

  it("survives a missing platform", () => {
    expect(guideFor(undefined).steps.length).toBeGreaterThan(0);
  });

  it("only links to https pages", () => {
    for (const guide of Object.values(PLATFORM_GUIDES)) {
      if (guide.setupUrl) expect(guide.setupUrl).toMatch(/^https:\/\//);
    }
  });

  it("gives every buildable platform at least one step", () => {
    for (const key of ["devto", "hashnode", "medium", "wordpress", "mastodon", "bluesky", "buttondown", "git"]) {
      expect(PLATFORM_GUIDES[key].steps.length).toBeGreaterThan(0);
    }
  });
});

describe("groupPlatforms", () => {
  it("handles no data yet", () => {
    const g = groupPlatforms(null);
    expect(g.total).toBe(0);
    expect(g.connected).toEqual([]);
  });

  it("splits connected, available and coming soon", () => {
    const g = groupPlatforms([
      p("devto", { connection: { status: "connected" } }),
      p("bluesky"),
      p("twitter", { implemented: false }),
    ]);
    expect(g.connected.map((x) => x.platform)).toEqual(["devto"]);
    expect(g.available.map((x) => x.platform)).toEqual(["bluesky"]);
    expect(g.comingSoon.map((x) => x.platform)).toEqual(["twitter"]);
    expect(g.total).toBe(2);
    expect(g.healthy).toBe(1);
  });

  it("keeps a stored connection on an unbuilt adapter with the connected ones", () => {
    const g = groupPlatforms([p("linkedin", { implemented: false, connection: { status: "connected" } })]);
    expect(g.connected).toHaveLength(1);
    expect(g.comingSoon).toHaveLength(0);
  });

  it("counts a rejected key as needing attention, not healthy", () => {
    const g = groupPlatforms([
      p("devto", { connection: { status: "invalid" } }),
      p("medium", { connection: { status: "connected" } }),
    ]);
    expect(g.attention.map((x) => x.platform)).toEqual(["devto"]);
    expect(g.healthy).toBe(1);
    expect(g.total).toBe(2);
  });
});
