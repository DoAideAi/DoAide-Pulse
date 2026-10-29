import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { redactSecrets } from "./activity";

// public/analytics-redact.js is a classic script that runs before the app
// bundle (see the file); loaded here the way the browser loads it.
beforeAll(() => {
  const source = readFileSync(resolve(__dirname, "../../public/analytics-redact.js"), "utf8");
  // eslint-disable-next-line no-new-func
  new Function(source)();
});

const TOKEN = "Zk3_q-9aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789";
const origin = () => window.location.origin;

describe("the Umami before-send hook", () => {
  it("takes a password-reset token out of the page URL and keeps the campaign tags", () => {
    const payload = window.pulseRedactAnalytics("event", {
      url: `/reset-password?token=${TOKEN}&utm_source=mail`,
    });
    expect(payload.url).toBe("/reset-password?token=redacted&utm_source=mail");
  });

  it("takes a preview token out of the path", () => {
    const payload = window.pulseRedactAnalytics("event", { url: `/preview/${TOKEN}` });
    expect(payload.url).toBe("/preview/:token");
  });

  it("cleans the referrer too — the next page's referrer is the page with the token", () => {
    const payload = window.pulseRedactAnalytics("event", {
      url: "/login",
      referrer: `${origin()}/reset-password?token=${TOKEN}`,
    });
    expect(payload.referrer).toBe(`${origin()}/reset-password?token=redacted`);
    expect(JSON.stringify(payload)).not.toContain(TOKEN);
  });

  it("leaves an ordinary page and an external referrer alone", () => {
    const payload = window.pulseRedactAnalytics("event", {
      url: "/blog/some-post?utm_campaign=launch",
      referrer: "https://www.google.com/",
    });
    expect(payload.url).toBe("/blog/some-post?utm_campaign=launch");
    expect(payload.referrer).toBe("https://www.google.com/");
  });

  it("applies the same path rule as the activity tracker", () => {
    for (const path of [`/preview/${TOKEN}`, "/content/7", "/preview/", "/article/preview"]) {
      expect(window.pulseRedactUrl(path)).toBe(redactSecrets(path));
    }
  });
});

describe("index.html", () => {
  const html = readFileSync(resolve(__dirname, "../../index.html"), "utf8");

  it("loads the hook before the tracker, blocking, and names it on the tracker", () => {
    const hook = html.indexOf('<script src="/analytics-redact.js"></script>');
    const tracker = html.indexOf("analytics.doaide.com/script.js");
    expect(hook).toBeGreaterThan(-1);
    expect(hook).toBeLessThan(tracker);
    expect(html).toMatch(/script\.js"[^>]*data-before-send="pulseRedactAnalytics"/);
  });
});
