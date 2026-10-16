import { describe, expect, it } from "vitest";
import { explainPublishError } from "./publishErrors";

const kind = (error) => explainPublishError(error)?.kind ?? null;

describe("explainPublishError", () => {
  it("says nothing about nothing", () => {
    expect(explainPublishError(null)).toBeNull();
    expect(explainPublishError("")).toBeNull();
    expect(explainPublishError(undefined)).toBeNull();
  });

  it("says nothing rather than guessing at an unrecognised error", () => {
    expect(explainPublishError("Bluesky returned no record uri: {}")).toBeNull();
  });

  it("points a missing connection at Settings", () => {
    const out = explainPublishError("No live devto connection — add one in Settings.");
    expect(out.kind).toBe("not_connected");
    expect(out.action).toEqual({ label: "Open Settings", to: "/settings" });
  });

  it.each([
    "401 Unauthorized",
    "Hashnode rejected the request: Unauthorized",
    "Dev.to accepted the key but returned no account",
    "HTTP 403 Forbidden",
    "invalid api_key",
    "The token has expired",
  ])("reads %j as a credentials problem with a way to fix it", (error) => {
    const out = explainPublishError(error);
    expect(out.kind).toBe("credentials");
    expect(out.action.to).toBe("/settings");
  });

  it("tells a paused platform apart from a broken one", () => {
    expect(
      kind(
        "Paused: recent publishes to this platform have been failing. " +
          "Waiting for it to recover before trying again.",
      ),
    ).toBe("paused");
  });

  it("reads a rate limit as rate limited, even while it backs off", () => {
    expect(kind("429 Too Many Requests — retrying in 120s")).toBe("rate_limited");
  });

  it("reads a transient failure that is backing off", () => {
    expect(kind("connection reset — retrying in 30s")).toBe("backing_off");
    expect(
      kind("The worker publishing this stopped before it finished — retrying."),
    ).toBe("backing_off");
  });

  it("recognises a timeout", () => {
    expect(kind("Publishing timed out — the platform took too long to answer")).toBe(
      "timeout",
    );
  });

  it("sends a missing title back to the editor", () => {
    expect(kind("Dev.to requires a title and this piece has none.")).toBe("needs_title");
  });

  it("treats an archived or withdrawn piece as deliberate", () => {
    expect(kind("This piece was archived before it went out.")).toBe("withdrawn");
    expect(kind("The piece was moved back before it went out.")).toBe("withdrawn");
  });

  it("does not tell a deactivated account to re-approve", () => {
    expect(kind("The account was deactivated before this went out.")).toBeNull();
  });

  it("recognises a platform-side server error", () => {
    expect(kind("HTTP 502 Bad Gateway")).toBe("server");
  });
});
