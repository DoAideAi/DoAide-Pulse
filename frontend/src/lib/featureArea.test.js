import { describe, expect, it } from "vitest";
import { FEATURE_AREAS, OTHER_AREA, describeBrowser, featureFor } from "./featureArea";

describe("featureFor", () => {
  it.each([
    ["/content/42", "Content Editor"],
    ["/content", "Content Library"],
    ["/content/", "Content Library"],
    ["/analytics", "Analytics"],
    ["/my-templates", "Templates"],
    ["/templates", "Templates"],
    ["/calendar", "Calendar"],
    ["/settings", "Settings"],
    ["/publish", "Publishing"],
    ["/tools/subject-line-tester", "Free Tools"],
    ["/blog/some-post", "Blog"],
    ["/admin/feedback", "Feedback Admin"],
    ["/", "Landing Page"],
  ])("%s is %s", (path, area) => {
    expect(featureFor(path)).toBe(area);
  });

  it("calls a path no rule names Other", () => {
    expect(featureFor("/nowhere/at/all")).toBe(OTHER_AREA);
    expect(featureFor("")).toBe("Landing Page");
  });

  it("offers every detectable area, plus Translations and Other, once each", () => {
    expect(FEATURE_AREAS).toContain("Translations");
    expect(FEATURE_AREAS).toContain("Content Editor");
    expect(FEATURE_AREAS[FEATURE_AREAS.length - 1]).toBe(OTHER_AREA);
    expect(new Set(FEATURE_AREAS).size).toBe(FEATURE_AREAS.length);
  });
});

describe("describeBrowser", () => {
  it.each([
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0 Safari/537.36", "Chrome on macOS"],
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36 Edg/130.0", "Edge on Windows"],
    ["Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0", "Firefox on Linux"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1", "Safari on iOS"],
    ["", "Unknown browser"],
  ])("%s", (ua, expected) => {
    expect(describeBrowser(ua)).toBe(expected);
  });
});
