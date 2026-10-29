/**
 * Who the app thinks you are, and what it does with a token it cannot use.
 *
 * `App.test.jsx` mocks this hook wholesale so it can test the route table, so
 * the provider itself has never been rendered. What that leaves unasserted is
 * the bootstrap: a stored token is believed only as far as `/auth/me`, and a
 * token the server rejects has to be cleared rather than left to fail the next
 * request too. Everything downstream — which routes render, whether the app
 * shows a sign-in page — is decided by `user` and `loading` coming out of here.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./useAuth";
import { api, getToken, setToken } from "../lib/api";
import { whileCaught } from "../test/caught";

vi.mock("../lib/api", () => ({
  api: {
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  },
  getToken: vi.fn(),
  setToken: vi.fn(),
  SESSION_ENDED: "pulse:session-ended",
  TOKEN_KEY: "pulse_token",
}));

const ME = { id: 1, email: "writer@example.com", connected_platforms: [] };

function draw() {
  return renderHook(() => useAuth(), { wrapper: AuthProvider });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("starting up with no token", () => {
  it("does not ask the server who you are", async () => {
    getToken.mockReturnValue(null);
    const { result } = draw();

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.me).not.toHaveBeenCalled();
    expect(result.current.user).toBeNull();
  });

  it("stops loading, so the app can show the sign-in page", async () => {
    // Left loading forever, the router would render nothing at all.
    getToken.mockReturnValue(null);
    const { result } = draw();

    await waitFor(() => expect(result.current.loading).toBe(false));
  });
});

describe("starting up with a stored token", () => {
  it("believes it only as far as /auth/me", async () => {
    getToken.mockReturnValue("stored-token");
    api.me.mockResolvedValue(ME);
    const { result } = draw();

    await waitFor(() => expect(result.current.user).toEqual(ME));
    expect(api.me).toHaveBeenCalledTimes(1);
    expect(result.current.loading).toBe(false);
  });

  it("throws away a token the server will not accept", async () => {
    // Otherwise every request for the rest of the session carries a token
    // already known to be dead, and each one fails on its own.
    getToken.mockReturnValue("expired-token");
    api.me.mockRejectedValue(new Error("401"));
    const { result } = draw();

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(setToken).toHaveBeenCalledWith(null);
    expect(result.current.user).toBeNull();
  });
});

describe("a session the server stops accepting", () => {
  // api.js clears the token on a 401 and announces it; until this the app
  // kept its user, and every later action failed on a page that still looked
  // signed in.
  it("signs the app out, so the route guard can take the user to sign in", async () => {
    getToken.mockReturnValue("token");
    api.me.mockResolvedValue(ME);
    const { result } = draw();
    await waitFor(() => expect(result.current.user).toEqual(ME));

    act(() => {
      window.dispatchEvent(new Event("pulse:session-ended"));
    });

    expect(result.current.user).toBeNull();
    expect(window.sessionStorage.getItem("pulse:session-ended")).toBe("1");
    window.sessionStorage.clear();
  });
});

describe("signing in", () => {
  it("reads the user back rather than assuming the login response is one", async () => {
    getToken.mockReturnValue(null);
    api.login.mockResolvedValue({ access_token: "fresh" });
    api.me.mockResolvedValue(ME);
    const { result } = draw();
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login("writer@example.com", "hunter2");
    });

    expect(api.login).toHaveBeenCalledWith("writer@example.com", "hunter2");
    expect(result.current.user).toEqual(ME);
  });

  it("lets a failed sign-in through to the caller", async () => {
    // The login form is what shows the message; swallowing it here would
    // leave the form spinning on a password that was simply wrong.
    getToken.mockReturnValue(null);
    api.login.mockRejectedValue(new Error("Incorrect email or password"));
    const { result } = draw();
    await waitFor(() => expect(result.current.loading).toBe(false));

    await expect(
      act(async () => {
        await result.current.login("writer@example.com", "wrong");
      }),
    ).rejects.toThrow("Incorrect email or password");
    expect(result.current.user).toBeNull();
  });
});

describe("registering", () => {
  it("signs the new account straight in", async () => {
    getToken.mockReturnValue(null);
    api.register.mockResolvedValue({ id: 1 });
    api.login.mockResolvedValue({ access_token: "fresh" });
    api.me.mockResolvedValue(ME);
    const { result } = draw();
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.register("writer@example.com", "hunter2", "A Writer");
    });

    // The fourth argument is the invite code (4bbf1bc): none here.
    expect(api.register).toHaveBeenCalledWith(
      "writer@example.com",
      "hunter2",
      "A Writer",
      undefined,
    );
    expect(api.login).toHaveBeenCalledWith("writer@example.com", "hunter2");
    expect(result.current.user).toEqual(ME);
  });
});

describe("signing out", () => {
  it("drops the token and the user together", async () => {
    getToken.mockReturnValue("stored-token");
    api.me.mockResolvedValue(ME);
    const { result } = draw();
    await waitFor(() => expect(result.current.user).toEqual(ME));

    act(() => result.current.logout());

    expect(api.logout).toHaveBeenCalled();
    expect(result.current.user).toBeNull();
  });
});

describe("refreshing", () => {
  it("re-reads the user, because connecting a platform changes it", async () => {
    getToken.mockReturnValue("stored-token");
    api.me.mockResolvedValue(ME);
    const { result } = draw();
    await waitFor(() => expect(result.current.user).toEqual(ME));

    const connected = { ...ME, connected_platforms: ["devto"] };
    api.me.mockResolvedValue(connected);
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.user).toEqual(connected);
  });

  it("is a no-op once signed out", async () => {
    // Called from a settings page that can still be on screen for a moment
    // after the token went away; without the guard it is a guaranteed 401.
    getToken.mockReturnValue(null);
    api.me.mockResolvedValue(ME);
    const { result } = draw();
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.refresh();
    });

    expect(api.me).not.toHaveBeenCalled();
    expect(result.current.user).toBeNull();
  });
});

describe("outside the provider", () => {
  it("throws rather than reporting everyone as signed out", async () => {
    // The dangerous failure: a null context read as "no user" would send a
    // signed-in author to the sign-in page with no way to tell why.
    await whileCaught(() => {
      expect(() => renderHook(() => useAuth())).toThrow(/within AuthProvider/);
    });
  });
});


// The token is in localStorage, shared by every tab; `user` was not. Signing out
// in one tab left the others showing the account — and once somebody else
// signed in on that browser, a stale tab went on showing the first account's
// pages while its requests carried the second account's token.
describe("another tab changes the session", () => {
  async function signedIn() {
    getToken.mockReturnValue("token-1");
    api.me.mockResolvedValue(ME);
    const view = draw();
    await waitFor(() => expect(view.result.current.user).toEqual(ME));
    return view;
  }

  function storage(key, newValue) {
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key, newValue }));
    });
  }

  it("signs this tab out when that one signs out", async () => {
    const { result } = await signedIn();

    getToken.mockReturnValue(null);
    storage("pulse_token", null);

    expect(result.current.user).toBeNull();
  });

  it("signs this tab out when the whole storage is cleared", async () => {
    const { result } = await signedIn();

    getToken.mockReturnValue(null);
    storage(null, null);

    expect(result.current.user).toBeNull();
  });

  it("does not carry on as one account under another account's token", async () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    try {
      const { result } = await signedIn();

      getToken.mockReturnValue("token-2");
      api.me.mockResolvedValue({ ...ME, id: 2, email: "someone@example.com" });
      storage("pulse_token", "token-2");

      await waitFor(() => expect(reload).toHaveBeenCalled());
      expect(result.current.user?.id).not.toBe(2);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("takes the same account's new token without a reload", async () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    try {
      const { result } = await signedIn();

      getToken.mockReturnValue("token-1b");
      api.me.mockResolvedValue({ ...ME, full_name: "Renamed" });
      storage("pulse_token", "token-1b");

      await waitFor(() => expect(result.current.user?.full_name).toBe("Renamed"));
      expect(reload).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("ignores every other key", async () => {
    const { result } = await signedIn();
    api.me.mockClear();

    storage("pulse:theme", "dark");

    expect(api.me).not.toHaveBeenCalled();
    expect(result.current.user).toEqual(ME);
  });
});
