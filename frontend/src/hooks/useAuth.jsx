import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, SESSION_ENDED, setToken } from "../lib/api";
import trackEvent from "../lib/trackEvent";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

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
