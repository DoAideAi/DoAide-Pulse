import { createContext, useContext, useEffect, useRef, useState } from "react";
import { api, getToken, SESSION_ENDED, setToken, TOKEN_KEY } from "../lib/api";
import trackEvent from "../lib/trackEvent";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const userRef = useRef(null);
  userRef.current = user;

  // The API refused the session (expired, revoked by a password reset, or the
  // account switched off). Signed out here too, so the route guard takes the
  // user to the sign-in form — which says why — instead of leaving them on a
  // page where every action fails.
  useEffect(() => {
    function ended() {
      try {
        window.sessionStorage.setItem(SESSION_ENDED, "1");
      } catch {
        // Private mode: the redirect still happens, just without the notice.
      }
      setUser(null);
    }
    window.addEventListener(SESSION_ENDED, ended);
    return () => window.removeEventListener(SESSION_ENDED, ended);
  }, []);

  // The token is in localStorage, which every tab shares; `user` is per tab.
  // Another tab signing out, or signing in, changes the token under this one,
  // and nothing told this tab: it went on showing the account after a sign-out,
  // and after somebody else signed in it showed the first account's pages while
  // sending the second account's token. A `storage` event is that news — it
  // only fires in the *other* tabs, never the one that made the change.
  useEffect(() => {
    function onStorage(event) {
      // `key` is null when the whole storage was cleared.
      if (event.key !== TOKEN_KEY && event.key !== null) return;
      if (!getToken()) {
        setUser(null);
        return;
      }
      api
        .me()
        .then((next) => {
          const current = userRef.current;
          // A different account: everything on this page — loaded lists, an
          // open editor — belongs to the old one, so start the page over.
          if (current && next?.id !== current.id) window.location.reload();
          else setUser(next);
        })
        .catch(() => setUser(null));
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  async function login(email, password) {
    await api.login(email, password);
    setUser(await api.me());
    trackEvent("login");
  }

  async function register(email, password, fullName, inviteToken) {
    await api.register(email, password, fullName, inviteToken);
    await login(email, password);
    trackEvent("signup");
  }

  function logout() {
    api.logout();
    setUser(null);
    trackEvent("logout");
  }

  /** Re-read the user — connecting a platform changes connected_platforms. */
  async function refresh() {
    if (!getToken()) return;
    setUser(await api.me());
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
