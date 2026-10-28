import { describe, expect, it } from "vitest";
import { isRetryableSaveError } from "./ContentEditor";

describe("isRetryableSaveError", () => {
  it("retries a save that never got an answer", () => {
    // The API client reports a network failure as status 0.
    expect(isRetryableSaveError({ status: 0 })).toBe(true);
    expect(isRetryableSaveError(new Error("no status"))).toBe(true);
  });

  it("retries the server's 'not now' answers and nothing else", () => {
    expect(isRetryableSaveError({ status: 503 })).toBe(true);
    expect(isRetryableSaveError({ status: 429 })).toBe(true);
    expect(isRetryableSaveError({ status: 412 })).toBe(false);
    expect(isRetryableSaveError({ status: 422 })).toBe(false);
  });
});
