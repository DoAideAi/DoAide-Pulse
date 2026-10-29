// What the API client does with a response that is not Pulse's.
//
// Every error the UI shows comes out of `request`, and the shape it reads —
// `{detail: "..."}` — is FastAPI's. But not everything that answers a fetch is
// FastAPI: a gateway timeout, a proxy's request-too-large page and a plain HTML
// error page all arrive here as text. Parsing those as JSON threw a SyntaxError
// whose message is "Unexpected token '<'", and *that* is what landed in the
// toast — a browser diagnostic in place of the status that would have told the
// user what happened.

import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";

import { api, getToken, setToken } from "./api";

/** Stand in for one fetch round trip. */
function respondWith({ status = 200, body = "", statusText = "" } = {}) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText,
    text: async () => body,
  });
}

describe("request", () => {
  beforeEach(() => {
    setToken(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("says the request did not get through instead of quoting the browser", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const error = await api.listProjects().catch((e) => e);
    expect(error.message).toMatch(/couldn't reach pulse/i);
    expect(error.message).not.toMatch(/failed to fetch/i);
    expect(error.status).toBe(0);
  });

  // Over HTTP/2 there is no reason phrase, so these used to reach the toast as
  // a bare "HTTP 502" — during every deploy's restart — and a 504 on a slow
  // write invited an immediate retry of something that may have finished.
  it("explains a gateway error that is not Pulse's, and keeps the status", async () => {
    vi.stubGlobal(
      "fetch",
      respondWith({ status: 502, body: "<html><body>502 Bad Gateway</body></html>" }),
    );

    const error = await api.listProjects().catch((e) => e);
    expect(error.message).toMatch(/restarting or briefly unreachable/i);
    expect(error.message).not.toMatch(/^HTTP 502$/);
    expect(error.status).toBe(502);
  });

  it("says a timed-out request may still have gone through", async () => {
    vi.stubGlobal("fetch", respondWith({ status: 504, statusText: "Gateway Timeout", body: "timeout" }));

    const error = await api.listProjects().catch((e) => e);
    expect(error.message).toMatch(/may still have finished/i);
    expect(error.message).not.toMatch(/unexpected token/i);
    expect(error.status).toBe(504);
  });

  it("says what a proxy's too-large refusal means", async () => {
    vi.stubGlobal("fetch", respondWith({ status: 413, statusText: "", body: "too big" }));

    await expect(api.listProjects()).rejects.toThrow(/too large/i);
  });

  it("falls back to the status code for anything else with no detail", async () => {
    vi.stubGlobal("fetch", respondWith({ status: 418, statusText: "", body: "teapot" }));

    await expect(api.listProjects()).rejects.toThrow("HTTP 418");
  });

  it("still prefers Pulse's own 503 detail over the generic wording", async () => {
    vi.stubGlobal(
      "fetch",
      respondWith({
        status: 503,
        body: JSON.stringify({ detail: "The database is unavailable for a moment" }),
      }),
    );

    await expect(api.listProjects()).rejects.toThrow("The database is unavailable for a moment");
  });

  it("still prefers FastAPI's own detail when there is one", async () => {
    vi.stubGlobal(
      "fetch",
      respondWith({
        status: 409,
        statusText: "Conflict",
        body: JSON.stringify({ detail: "Already published" }),
      }),
    );

    await expect(api.listProjects()).rejects.toThrow("Already published");
  });

  it("joins a validation error's messages", async () => {
    vi.stubGlobal(
      "fetch",
      respondWith({
        status: 422,
        body: JSON.stringify({
          detail: [{ msg: "field required" }, { msg: "too long" }],
        }),
      }),
    );

    await expect(api.listProjects()).rejects.toThrow("field required, too long");
  });

  it("names the field each validation message is about", async () => {
    vi.stubGlobal(
      "fetch",
      respondWith({
        status: 422,
        body: JSON.stringify({
          detail: [
            { loc: ["body", "password"], msg: "String should have at least 8 characters" },
            { loc: ["body", "variables", 0, "name"], msg: "Value error, 'a b' is not a usable variable name." },
            { loc: ["body"], msg: "Input should be a valid dictionary" },
          ],
        }),
      }),
    );

    await expect(api.listProjects()).rejects.toThrow(
      "Password: String should have at least 8 characters, " +
        "Name: 'a b' is not a usable variable name., " +
        "Input should be a valid dictionary",
    );
  });

  it.each([
    // A union field that failed every member names the field, not the type.
    [{ loc: ["body", "count", "int"], msg: "Input should be a valid integer" }, "Count: Input should be a valid integer"],
    [{ loc: ["body", "when", "function-after[_aware(), datetime]"], msg: "bad" }, "When: bad"],
    [{ loc: ["body", "items", 0, "Var", "name"], msg: "too short" }, "Name: too short"],
    // An error on one item of a list says which item, counting from one.
    [{ loc: ["body", "tags", 3], msg: "Input should be a valid string" }, "Tags (item 4): Input should be a valid string"],
    // An index before the field is the container, not the location.
    [{ loc: ["body", "variables", 0, "name"], msg: "required" }, "Name: required"],
    [{ loc: ["query", "limit"], msg: "too big" }, "Limit: too big"],
    [{ loc: ["body", 2], msg: "bad item" }, "bad item"],
    [{ loc: [], msg: "Value error, whole body wrong" }, "whole body wrong"],
    [{ msg: "no loc at all" }, "no loc at all"],
  ])("describes %j as %j", async (error, expected) => {
    vi.stubGlobal(
      "fetch",
      respondWith({ status: 422, body: JSON.stringify({ detail: [error] }) }),
    );
    await expect(api.listProjects()).rejects.toThrow(expected);
  });

  it("returns null rather than throwing for an empty 204 body", async () => {
    vi.stubGlobal("fetch", respondWith({ status: 204, body: "" }));

    await expect(api.deleteProject(1)).resolves.toBeNull();
  });

  it("says so when a body is cut off mid-read, not the browser's 'network error'", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: "OK",
        text: async () => {
          throw new TypeError("network error");
        },
      }),
    );

    const error = await api.exportAccount().catch((e) => e);

    expect(error.message).toMatch(/stopped answering part-way through/);
    expect(error.message).not.toMatch(/network error/);
    expect(error.status).toBe(0);
  });

  it("refuses a success whose body is cut short instead of returning null", async () => {
    // The account export saved a file containing `null` from exactly this.
    vi.stubGlobal("fetch", respondWith({ status: 200, body: '{"account": {"email": "a@' }));

    await expect(api.exportAccount()).rejects.toThrow(/arrived cut off/);
  });

  it("clears a token the server has stopped accepting", async () => {
    setToken("stale");
    vi.stubGlobal("fetch", respondWith({ status: 401, statusText: "Unauthorized" }));

    await expect(api.me()).rejects.toThrow();
    expect(getToken()).toBeNull();
  });

  it("announces a refused session, so the app can sign the user out", async () => {
    setToken("stale");
    vi.stubGlobal("fetch", respondWith({ status: 401, statusText: "Unauthorized" }));
    const heard = vi.fn();
    window.addEventListener("pulse:session-ended", heard);

    await expect(api.me()).rejects.toThrow();

    window.removeEventListener("pulse:session-ended", heard);
    expect(heard).toHaveBeenCalledTimes(1);
  });

  it("does not announce one for a failed sign-in, which carried no session", async () => {
    setToken(null);
    vi.stubGlobal("fetch", respondWith({ status: 401, statusText: "Unauthorized" }));
    const heard = vi.fn();
    window.addEventListener("pulse:session-ended", heard);

    await expect(api.login("a@example.com", "wrong")).rejects.toThrow();

    window.removeEventListener("pulse:session-ended", heard);
    expect(heard).not.toHaveBeenCalled();
  });

  it("stringifies a detail that is neither a string nor a validation list", async () => {
    vi.stubGlobal(
      "fetch",
      respondWith({ status: 400, body: JSON.stringify({ detail: { code: 7 } }) }),
    );

    await expect(api.listProjects()).rejects.toThrow('{"code":7}');
  });
});

/**
 * What `request` puts on the wire.
 *
 * Everything above is about reading a response; none of it looks at the request
 * that produced one. But the three decisions this function makes before the
 * fetch — whether to attach the bearer token, whether the body is JSON or a
 * form, and which query parameters survive — are each load-bearing and each
 * silent when wrong. A `Content-Type: application/json` on the login form is a
 * 422 from FastAPI's OAuth2 form parser; an `Authorization` header on the
 * public preview endpoint turns a link anyone can open into one only its author
 * can; and `?status=` reaches the API as an empty string rather than as the
 * absence of a filter.
 */
describe("the outgoing request", () => {
  /** The single fetch call `fn` made, as `[url, init]`. */
  function sentBy(fetchMock) {
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    return { url, init };
  }

  function stubOk(body = "{}") {
    const fetchMock = respondWith({ status: 200, body });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  beforeEach(() => {
    setToken(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("attaches the stored token as a bearer credential", async () => {
    setToken("abc123");
    const fetchMock = stubOk();

    await api.me();

    const { url, init } = sentBy(fetchMock);
    expect(url).toBe("/api/v1/auth/me");
    expect(init.headers.Authorization).toBe("Bearer abc123");
  });

  it("sends no credential at all when there is no token", async () => {
    const fetchMock = stubOk();

    await api.me();

    expect(sentBy(fetchMock).init.headers).not.toHaveProperty("Authorization");
  });

  it("keeps the token off the endpoints that are public by design", async () => {
    setToken("abc123");
    const fetchMock = stubOk();

    await api.publicPreview("tok");

    const { url, init } = sentBy(fetchMock);
    expect(url).toBe("/api/v1/content/preview/tok");
    expect(init.headers).not.toHaveProperty("Authorization");
  });

  it("authenticates the detail health check even though the probe is public", async () => {
    setToken("abc123");
    const publicProbe = stubOk();
    await api.health();
    expect(sentBy(publicProbe).init.headers).not.toHaveProperty("Authorization");

    vi.unstubAllGlobals();
    const detail = stubOk();
    await api.healthDetail();
    expect(sentBy(detail).init.headers.Authorization).toBe("Bearer abc123");
  });

  it("encodes a JSON body and declares it", async () => {
    const fetchMock = stubOk();

    await api.createProject({ name: "Pulse" });

    const { url, init } = sentBy(fetchMock);
    expect(url).toBe("/api/v1/projects");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe('{"name":"Pulse"}');
  });

  it("hands a form through untouched, so the browser sets its own content type", async () => {
    const fetchMock = stubOk(JSON.stringify({ access_token: "t" }));

    await api.login("you@example.com", "pw");

    const { url, init } = sentBy(fetchMock);
    expect(url).toBe("/api/v1/auth/login");
    expect(init.headers).not.toHaveProperty("Content-Type");
    expect(init.body).toBeInstanceOf(URLSearchParams);
    expect(init.body.get("username")).toBe("you@example.com");
    expect(init.body.get("password")).toBe("pw");
  });

  it("sends no body and no content type on a plain read", async () => {
    const fetchMock = stubOk("[]");

    await api.listProjects();

    const { init } = sentBy(fetchMock);
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
    expect(init.headers).not.toHaveProperty("Content-Type");
  });

  it("makes a save conditional on the version the caller was editing", async () => {
    // Quoted, because the backend parses an entity tag and refuses a bare
    // number with a 400 — a save sent unquoted would fail every time.
    const fetchMock = stubOk();

    await api.updateContent(3, { title: "t" }, 4);

    expect(sentBy(fetchMock).init.headers["If-Match"]).toBe('"4"');
  });

  it("saves unconditionally when the caller has no version to offer", async () => {
    const fetchMock = stubOk();

    await api.updateContent(3, { title: "t" });

    expect(sentBy(fetchMock).init.headers).not.toHaveProperty("If-Match");
  });

  it("treats version 0 as a version rather than as an absence", async () => {
    // `== null` on purpose: `!version` would drop a legitimate 0. No row has
    // one today — the column starts at 1 — but a falsy-check that happens to be
    // right is a guard that silently stops guarding when the numbering changes.
    const fetchMock = stubOk();

    await api.updateContent(3, { title: "t" }, 0);

    expect(sentBy(fetchMock).init.headers["If-Match"]).toBe('"0"');
  });

  it("stores the token a successful login returns", async () => {
    stubOk(JSON.stringify({ access_token: "fresh", token_type: "bearer" }));

    await api.login("you@example.com", "pw");

    expect(getToken()).toBe("fresh");
  });

  it("registers without a token, so a signed-out browser can", async () => {
    setToken("someone-elses");
    const fetchMock = stubOk();

    await api.register("you@example.com", "pw", "You");

    const { init } = sentBy(fetchMock);
    expect(init.headers).not.toHaveProperty("Authorization");
    expect(JSON.parse(init.body)).toEqual({
      email: "you@example.com",
      password: "pw",
      full_name: "You",
    });
  });

  it("sends an invite code when there is one, and only then", async () => {
    const fetchMock = stubOk();

    await api.register("you@example.com", "pw", null, "welcome-42");

    expect(JSON.parse(sentBy(fetchMock).init.body)).toEqual({
      email: "you@example.com",
      password: "pw",
      full_name: null,
      invite_token: "welcome-42",
    });
  });

  it("forgets the token on logout", () => {
    vi.stubGlobal("fetch", respondWith({ status: 204 }));
    setToken("abc123");

    api.logout();

    expect(getToken()).toBeNull();
    vi.unstubAllGlobals();
  });

  // Forgetting the token was all "Sign out" did, so the token itself stayed
  // valid for its whole lifetime. The server has to be told.
  it("tells the server, with the token it is signing out", async () => {
    const fetchMock = respondWith({ status: 204 });
    vi.stubGlobal("fetch", fetchMock);
    setToken("abc123");

    await api.logout();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/auth/logout");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer abc123");
    vi.unstubAllGlobals();
  });

  it("signs out locally even when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    setToken("abc123");

    await expect(api.logout()).resolves.toBeUndefined();
    expect(getToken()).toBeNull();
    vi.unstubAllGlobals();
  });

  it("does not call the server when there was no session", async () => {
    const fetchMock = respondWith({ status: 204 });
    vi.stubGlobal("fetch", fetchMock);
    setToken(null);

    await api.logout();

    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe("query strings", () => {
  function stubOk() {
    const fetchMock = respondWith({ status: 200, body: "[]" });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("omits the question mark entirely when nothing is being filtered", async () => {
    const fetchMock = stubOk();

    await api.listContent();

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/content");
  });

  it("drops a filter the user cleared rather than sending it empty", async () => {
    const fetchMock = stubOk();

    await api.listContent({ status: "", project_id: 4, q: null });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/content?project_id=4");
  });

  it("keeps a zero, which is a value and not an absence", async () => {
    const fetchMock = stubOk();

    await api.listContent({ offset: 0, limit: 25 });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/content?offset=0&limit=25");
  });

  it("escapes a value that would otherwise break the query", async () => {
    const fetchMock = stubOk();

    await api.listContent({ q: "a&b=c d" });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/content?q=a%26b%3Dc+d");
  });

  it("sends no window when the caller did not choose one", async () => {
    const fetchMock = stubOk();

    await api.engagementTrend(undefined);

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/analytics/engagement-trend");
  });
});

/**
 * Endpoints whose method or body is easy to get wrong by one character, and
 * where getting it wrong is a 404 or a 405 rather than anything the UI can
 * explain. The preview-link pair is the sharp one: `create` is the only
 * response that will ever contain the URL, and its body differs by whether the
 * caller chose a lifetime.
 */
describe("endpoint shapes", () => {
  function stubOk() {
    const fetchMock = respondWith({ status: 200, body: "{}" });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts an empty body for a preview link with no chosen lifetime", async () => {
    const fetchMock = stubOk();

    await api.createPreviewLink(9, undefined);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/content/9/preview-links");
    expect(init.method).toBe("POST");
    expect(init.body).toBe("{}");
  });

  it("carries the lifetime when one was chosen", async () => {
    const fetchMock = stubOk();

    await api.createPreviewLink(9, 48);

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ ttl_hours: 48 });
  });

  it("revokes a link by id under its own content", async () => {
    const fetchMock = stubOk();

    await api.revokePreviewLink(9, 3);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/content/9/preview-links/3");
    expect(init.method).toBe("DELETE");
  });

  it("patches rather than replaces on every update", async () => {
    for (const [call, url] of [
      [() => api.updateProject(1, { name: "x" }), "/api/v1/projects/1"],
      [() => api.updateContent(2, { title: "x" }), "/api/v1/content/2"],
      [() => api.updateTrigger(3, { active: false }), "/api/v1/triggers/3"],
      [() => api.updateTemplate(4, { name: "x" }), "/api/v1/templates/4"],
      [() => api.reschedule(5, { scheduled_for: null }), "/api/v1/calendar/content/5"],
    ]) {
      const fetchMock = stubOk();
      await call();
      expect(fetchMock.mock.calls[0][0]).toBe(url);
      expect(fetchMock.mock.calls[0][1].method).toBe("PATCH");
      vi.unstubAllGlobals();
    }
  });

  it("puts a connection, because saving one twice must not make two", async () => {
    const fetchMock = stubOk();

    await api.saveConnection("devto", { api_key: "k" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/settings/connections");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({
      platform: "devto",
      credentials: { api_key: "k" },
    });
  });

  it("retries one publication under its own content, not the whole piece", async () => {
    const fetchMock = stubOk();

    await api.retryPublication(7, 12);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/content/7/retry/12");
    expect(init.method).toBe("POST");
  });
});

/**
 * Every remaining endpoint, as a path and a verb.
 *
 * The cases above each exist because something specific about them was once
 * wrong. This block exists for the opposite reason: the methods it covers are
 * one-line wrappers with nothing interesting in them, which is exactly why a
 * typo in a path or a read left as the default GET survives review. Every page
 * test mocks this module wholesale, so without this the only thing checking
 * these strings was production.
 *
 * The list is asserted to be exhaustive at the end, so a new endpoint added
 * without a row here fails rather than passing unnoticed.
 */
describe("every endpoint's path and verb", () => {
  function stubOk() {
    const fetchMock = respondWith({ status: 200, body: "{}" });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // [method name, arguments, expected path, expected verb]
  const ENDPOINTS = [
    ["me", [], "/auth/me", "GET"],
    ["deleteAccount", ["pw"], "/auth/me", "DELETE"],
    ["health", [], "/health", "GET"],
    ["healthDetail", [], "/health/detail", "GET"],

    ["listProjects", [], "/projects", "GET"],
    ["createProject", [{ name: "H" }], "/projects", "POST"],
    ["updateProject", [5, { name: "H" }], "/projects/5", "PATCH"],
    ["deleteProject", [5], "/projects/5", "DELETE"],
    ["scanProject", [5], "/projects/5/scan", "POST"],
    ["draftProjectFromDocuments", [[]], "/projects/draft-from-documents", "POST"],

    ["listContent", [], "/content", "GET"],
    ["listContentPage", [{ limit: 100, offset: 0 }], "/content?limit=100&offset=0", "GET"],
    ["getContent", [3], "/content/3", "GET"],
    ["checkLinks", [3], "/content/3/links", "GET"],
    ["socialCards", [3], "/content/3/social", "GET"],
    ["generateContent", [{ project_id: 1 }], "/content/generate", "POST"],
    ["editPassage", [3, { selection: "x" }], "/content/3/edit", "POST"],
    ["updateContent", [3, { title: "t" }], "/content/3", "PATCH"],
    ["deleteContent", [3], "/content/3", "DELETE"],
    ["approveContent", [3], "/content/3/approve", "POST"],
    ["approveContent", [3, { force: true }], "/content/3/approve?force=true", "POST"],
    ["publishContent", [3, { platforms: [] }], "/content/3/publish", "POST"],
    ["retryPublication", [3, 8], "/content/3/retry/8", "POST"],
    ["reviewQueue", [], "/content/queue/review", "GET"],
    ["reviewQueuePage", [{ limit: 200, offset: 0 }], "/content/queue/review?limit=200&offset=0", "GET"],
    ["bulkApprove", [[1, 2]], "/content/bulk/approve", "POST"],
    ["bulkReject", [[1, 2]], "/content/bulk/reject", "POST"],
    ["bulkPublish", [[1, 2], ["devto"]], "/content/bulk/publish", "POST"],
    ["bulkRetry", [[1, 2]], "/content/bulk/retry", "POST"],
    ["publicationQueue", [], "/content/queue/publications?limit=200&offset=0", "GET"],
    ["setContentStatus", [3, "approved"], "/content/3/status", "POST"],
    ["archiveOld", [{ days: 30 }], "/content/bulk/archive-old", "POST"],
    ["listIdeas", [5], "/projects/5/ideas", "GET"],
    ["writeFromIdea", [9], "/content/ideas/9/write", "POST"],

    ["tagTree", [], "/tags", "GET"],
    ["suggestTags", [3], "/tags/suggest/3", "POST"],
    ["renameTags", [{ old: "a", new: "b" }], "/tags/rename", "POST"],

    ["listLanguages", [], "/languages", "GET"],
    ["listTranslations", [3], "/content/3/translations", "GET"],
    ["translateContent", [3, "hi"], "/content/3/translations", "POST"],
    ["deleteTranslation", [3, "hi"], "/content/3/translations/hi", "DELETE"],
    ["acceptTranslation", [3, "hi"], "/content/3/translations/hi/accept", "POST"],

    ["listRevisions", [3], "/content/3/revisions", "GET"],
    ["getRevision", [3, 2], "/content/3/revisions/2", "GET"],
    ["diffRevision", [3, 2], "/content/3/revisions/2/diff", "GET"],
    ["restoreRevision", [3, 2], "/content/3/revisions/2/restore", "POST"],

    ["listPreviewLinks", [3], "/content/3/preview-links", "GET"],
    ["createPreviewLink", [3], "/content/3/preview-links", "POST"],
    ["revokePreviewLink", [3, 9], "/content/3/preview-links/9", "DELETE"],
    ["publicPreview", ["tok"], "/content/preview/tok", "GET"],

    ["calendar", [], "/calendar", "GET"],
    ["reschedule", [3, { scheduled_for: null }], "/calendar/content/3", "PATCH"],
    ["calendarIdeas", [], "/calendar/ideas", "GET"],
    ["calendarIdeas", [{ start: "2026-10-01" }], "/calendar/ideas?start=2026-10-01", "GET"],
    ["createCalendarIdea", [{ project_id: 1, headline: "h" }], "/calendar/ideas", "POST"],
    ["planIdea", [4, "2026-10-30"], "/calendar/ideas/4", "PATCH"],
    ["planIdea", [4, null], "/calendar/ideas/4", "PATCH"],
    ["dismissIdea", [4], "/calendar/ideas/4", "DELETE"],

    ["dashboard", [], "/analytics/dashboard", "GET"],
    ["analytics", [], "/analytics/overview", "GET"],
    ["readTime", [], "/analytics/read-time", "GET"],
    ["engagementTrend", [30], "/analytics/engagement-trend?days=30", "GET"],
    ["velocity", [], "/analytics/velocity", "GET"],
    ["alerts", [5], "/analytics/alerts?limit=5", "GET"],
    ["pipeline", [], "/analytics/pipeline", "GET"],
    ["featureUsage", [30], "/analytics/features?days=30", "GET"],
    ["contentFunnel", [90, 7], "/analytics/funnel?days=90&stale_days=7", "GET"],
    ["contentFunnel", [], "/analytics/funnel", "GET"],
    ["autopilotEffectiveness", [90], "/analytics/autopilot?days=90", "GET"],
    ["subscriberGrowth", [30], "/analytics/subscribers?days=30", "GET"],
    ["activitySummary", [7], "/activity/summary?days=7", "GET"],
    ["productActivity", [7], "/products/activity?days=7", "GET"],
    ["productActivity", [1, { refresh: true }], "/products/activity?days=1&refresh=true", "GET"],
    ["submitFeedback", [{ message: "hi" }], "/feedback", "POST"],
    ["listFeedback", [{ category: "bug", feature: "" }], "/feedback?category=bug", "GET"],
    ["feedbackFeatures", [], "/feedback/features", "GET"],
    ["seoHealth", ["Asia/Kolkata"], "/seo/health?tz=Asia%2FKolkata", "GET"],
    ["seoHealthHistory", [90], "/seo/health/history?days=90", "GET"],
    ["seoSitemaps", [], "/seo/sitemaps", "GET"],
    ["seoSitemapRuns", [], "/seo/sitemaps/runs", "GET"],
    ["submitSitemaps", [], "/seo/sitemaps/submit", "POST"],
    ["submitSitemaps", ["gst"], "/seo/sitemaps/submit?site=gst", "POST"],
    ["seoAudit", [], "/seo/audit", "GET"],
    ["runSeoAudit", [], "/seo/audit", "POST"],
    ["runSeoAudit", ["gst"], "/seo/audit?site=gst", "POST"],
    ["seoTraffic", [30], "/seo/traffic?days=30", "GET"],
    ["seoTraffic", [7, { refresh: true }], "/seo/traffic?days=7&refresh=true", "GET"],
    ["seoPosts", [], "/seo/posts", "GET"],
    ["seoLinkSuggestions", [{ title: "t" }], "/seo/link-suggestions", "POST"],
    ["seoOptimalSlots", [["devto", "hashnode"]], "/seo/optimal-slots?platforms=devto&platforms=hashnode", "GET"],
    ["createContent", [{ title: "t" }], "/content", "POST"],
    ["scheduleContent", [3, { optimize: true }], "/content/3/schedule", "POST"],
    ["unscheduleContent", [3], "/content/3/schedule", "DELETE"],
    ["suggestHeadlines", [3, 4], "/content/3/headlines?count=4", "POST"],
    ["applyHeadline", [3, "New"], "/content/3/headlines/apply", "POST"],
    ["headlinePerformance", [3], "/content/3/headlines/performance", "GET"],
    ["headlineWinner", [3], "/content/3/headlines/winner", "GET"],
    ["adoptHeadlineWinner", [3], "/content/3/headlines/auto-select", "POST"],
    [
      "platformCheck",
      [3, ["devto", "bluesky"], true],
      "/content/3/platform-check?platforms=devto%2Cbluesky&as_draft=true",
      "GET",
    ],
    [
      "scheduleSuggestions",
      [3, ["devto", "mastodon"]],
      "/content/3/schedule/suggestions?platforms=devto&platforms=mastodon",
      "GET",
    ],

    ["redeliverWebhook", [4, 9], "/webhooks/4/deliveries/9/redeliver", "POST"],
    ["repurposeContent", [3], "/content/3/repurpose", "POST"],
    ["exportAccount", [], "/auth/me/export", "GET"],
    ["triggerKinds", [], "/triggers/kinds", "GET"],
    ["listTriggers", [], "/triggers", "GET"],
    ["createTrigger", [{ kind: "rss" }], "/triggers", "POST"],
    ["updateTrigger", [2, { is_active: false }], "/triggers/2", "PATCH"],
    ["deleteTrigger", [2], "/triggers/2", "DELETE"],
    ["rotateTriggerSecret", [2], "/triggers/2/rotate-secret", "POST"],
    ["checkTrigger", [2], "/triggers/2/check", "POST"],
    ["triggerEvents", [2], "/triggers/2/events", "GET"],

    ["templateBuiltins", [], "/templates/builtins", "GET"],
    ["listTemplates", [], "/templates", "GET"],
    ["getTemplate", [4], "/templates/4", "GET"],
    ["createTemplate", [{ name: "t" }], "/templates", "POST"],
    ["updateTemplate", [4, { name: "t" }], "/templates/4", "PATCH"],
    ["deleteTemplate", [4], "/templates/4", "DELETE"],
    ["previewTemplate", [4, { values: {} }], "/templates/4/preview", "POST"],
    ["useTemplate", [4, { values: {} }], "/templates/4/use", "POST"],

    ["publicArticle", ["test-slug"], "/articles/test-slug", "GET"],
    ["subscribe", ["a@b.com"], "/subscribers", "POST"],
    ["unsubscribe", ["a@b.com"], "/subscribers/unsubscribe", "POST"],
    ["generateContentIdeas", ["AI tools"], "/tools/content-ideas", "POST"],

    ["webhookEvents", [], "/webhooks/events", "GET"],
    ["listWebhooks", [], "/webhooks", "GET"],
    ["createWebhook", [{ url: "https://x.test", events: ["ping"] }], "/webhooks", "POST"],
    ["updateWebhook", [1, { is_active: false }], "/webhooks/1", "PATCH"],
    ["deleteWebhook", [1], "/webhooks/1", "DELETE"],
    ["rotateWebhookSecret", [1], "/webhooks/1/rotate-secret", "POST"],
    ["pingWebhook", [1], "/webhooks/1/ping", "POST"],
    ["webhookDeliveries", [1], "/webhooks/1/deliveries", "GET"],
    ["webhookDeliveriesPage", [3, { limit: 10 }], "/webhooks/3/deliveries?limit=10", "GET"],

    ["apiKeyScopes", [], "/api-keys/scopes", "GET"],
    ["listApiKeys", [], "/api-keys", "GET"],
    ["createApiKey", [{ project_id: 1, name: "k", scopes: ["content_read"] }], "/api-keys", "POST"],
    ["rotateApiKey", [1], "/api-keys/1/rotate", "POST"],
    ["revokeApiKey", [1], "/api-keys/1", "DELETE"],

    ["updateMe", [{ full_name: "J" }], "/auth/me", "PATCH"],
    ["requestPasswordReset", ["a@b.com"], "/auth/password-reset", "POST"],
    ["confirmPasswordReset", ["tok", "newpw"], "/auth/password-reset/confirm", "POST"],

    ["generateFields", [{ content_id: 1 }], "/ai/generate-fields", "POST"],

    ["platforms", [], "/settings/platforms", "GET"],
    ["saveConnection", ["devto", {}], "/settings/connections", "PUT"],
    ["verifyConnection", ["devto"], "/settings/connections/devto/verify", "POST"],
    ["deleteConnection", ["devto"], "/settings/connections/devto", "DELETE"],
    ["llmKey", [], "/settings/llm-key", "GET"],
    ["saveLlmKey", [{ provider: "gemini", api_key: "k" }], "/settings/llm-key", "PUT"],
    ["deleteLlmKey", [], "/settings/llm-key", "DELETE"],
  ];

  it("sends every document as a multipart `files` part", async () => {
    const fetchMock = stubOk();
    const a = new File(["a"], "a.md");
    const b = new File(["b"], "b.pdf");

    await api.draftProjectFromDocuments([a, b]);

    const [, init] = fetchMock.mock.calls[0];
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.body.getAll("files").map((f) => f.name)).toEqual(["a.md", "b.pdf"]);
  });

  it.each(ENDPOINTS)("%s hits %s as %s", async (name, args, path, verb) => {
    const fetchMock = stubOk();

    await api[name](...args);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`/api/v1${path}`);
    expect(init.method).toBe(verb);
  });

  it("sends the browser's zone with a template, so {{date.*}} is the writer's day", async () => {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    for (const name of ["previewTemplate", "useTemplate"]) {
      const fetchMock = stubOk();
      await api[name](4, { values: { a: "b" } });
      expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
        timezone: zone,
        values: { a: "b" },
      });
    }
    // A caller that names a zone keeps it.
    const fetchMock = stubOk();
    await api.previewTemplate(4, { values: {}, timezone: "Asia/Kolkata" });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).timezone).toBe("Asia/Kolkata");
  });

  it("covers every method on the client", () => {
    // `login`, `register` and `logout` are covered by their own cases above —
    // one sends a form, one is unauthenticated, and one touches no network at
    // all, so none of them fits the shape this table asserts. `queueCounts`
    // makes two requests and has its own case below.
    const exempt = new Set(["login", "register", "logout", "uploadImage", "queueCounts", "listAllTriggers"]);
    const covered = new Set(ENDPOINTS.map(([name]) => name));

    const uncovered = Object.keys(api).filter(
      (name) => !covered.has(name) && !exempt.has(name),
    );
    expect(uncovered).toEqual([]);
  });
});

describe("queueCounts", () => {
  afterEach(() => vi.unstubAllGlobals());

  function withTotals(totals) {
    return vi.fn(async (url) => ({
      ok: true,
      status: 200,
      statusText: "",
      headers: { get: (name) => (name === "X-Total-Count" ? totals(url) : null) },
      text: async () => "[]",
    }));
  }

  it("reads each queue's size from X-Total-Count, not the page", async () => {
    const fetchMock = withTotals((url) => (url.includes("status=failed") ? "7" : "120"));
    vi.stubGlobal("fetch", fetchMock);

    expect(await api.queueCounts()).toEqual({ review: 120, failed: 7 });
    const urls = fetchMock.mock.calls.map(([url]) => url);
    expect(urls).toContain("/api/v1/content/queue/review?limit=1");
    expect(urls).toContain("/api/v1/content/queue/publications?status=failed&limit=1");
  });

  it("falls back to the page length when a proxy drops the header", async () => {
    vi.stubGlobal("fetch", withTotals(() => null));

    expect(await api.queueCounts()).toEqual({ review: 0, failed: 0 });
  });
});

describe("listContentPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  function serving(body, total) {
    return vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "",
      headers: { get: (name) => (name === "X-Total-Count" ? total : null) },
      text: async () => body,
    }));
  }

  it("answers with the page and the total behind it", async () => {
    vi.stubGlobal("fetch", serving('[{"id":1},{"id":2}]', "240"));

    expect(await api.listContentPage({ limit: 2 })).toEqual({
      items: [{ id: 1 }, { id: 2 }],
      total: 240,
    });
  });

  it("counts the page when a proxy drops the header", async () => {
    vi.stubGlobal("fetch", serving('[{"id":1}]', null));

    expect(await api.listContentPage()).toEqual({ items: [{ id: 1 }], total: 1 });
  });
});

describe("listAllTriggers", () => {
  afterEach(() => vi.unstubAllGlobals());

  // The Triggers page took the default page of 100 and showed it as the whole
  // list; an account may hold a thousand. It reads until it has the total.
  it("reads every page until it has the total", async () => {
    const all = Array.from({ length: 1100 }, (_, i) => ({ id: i + 1 }));
    const fetchMock = vi.fn(async (url) => {
      const query = new URL(url, "http://x").searchParams;
      const limit = Number(query.get("limit"));
      const offset = Number(query.get("offset"));
      return {
        ok: true,
        status: 200,
        statusText: "",
        headers: { get: (n) => (n === "X-Total-Count" ? String(all.length) : null) },
        text: async () => JSON.stringify(all.slice(offset, offset + limit)),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    const triggers = await api.listAllTriggers({ project_id: 4 });

    expect(triggers).toHaveLength(1100);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[0][0]).toContain("project_id=4");
  });
});

describe("publicationQueue", () => {
  afterEach(() => vi.unstubAllGlobals());

  // The Publish page took the default page of 50 as the whole queue. A week of
  // scheduling across a few platforms is more than that, and a failed row
  // sorted after the fiftieth never appeared — while the sidebar badge, which
  // reads X-Total-Count, said it was there.
  it("reads every page until it has the whole queue", async () => {
    const all = Array.from({ length: 450 }, (_, i) => ({
      id: i + 1,
      status: i === 449 ? "failed" : "scheduled",
    }));
    const fetchMock = vi.fn(async (url) => {
      const query = new URL(url, "http://x").searchParams;
      const limit = Number(query.get("limit"));
      const offset = Number(query.get("offset"));
      return {
        ok: true,
        status: 200,
        statusText: "",
        headers: { get: (n) => (n === "X-Total-Count" ? String(all.length) : null) },
        text: async () => JSON.stringify(all.slice(offset, offset + limit)),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    const queue = await api.publicationQueue();

    expect(queue).toHaveLength(450);
    expect(queue.at(-1).status).toBe("failed");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
