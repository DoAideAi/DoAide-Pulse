import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import PublicNav from "../components/PublicNav";
import { api } from "../lib/api";
import { usePageMeta } from "../lib/pageMeta";

/**
 * Both halves of a password reset: ask for a link, and use one.
 *
 * The backend issued reset tokens and emailed a link to
 * ``/reset-password?token=…`` while the app had no such page — the link
 * landed on "not found", and nothing anywhere let a user ask for one. With a
 * token in the URL this sets the new password; without one it asks for the
 * address. The request answers the same whether or not an account exists, so
 * the confirmation here does not say "we found you" either.
 */
export default function ResetPassword() {
  usePageMeta({ title: "Reset your password | DoAide Pulse", path: "/reset-password" });
  const [params] = useSearchParams();
  // Read once, then taken out of the address bar: a credential for the whole
  // account should not sit in history, or go out as the next page's referrer.
  const [token] = useState(() => {
    const value = params.get("token");
    if (value && typeof window !== "undefined") {
      window.history.replaceState(window.history.state, "", window.location.pathname);
    }
    return value;
  });

  return (
    <div className="min-h-screen bg-canvas text-ink-700">
      <PublicNav />
      <main id="main" tabIndex={-1} className="mx-auto max-w-md px-4 py-16">
        <h1 className="font-display text-3xl text-ink-900">Reset your password</h1>
        {token ? <SetPassword token={token} /> : <RequestLink />}
        <p className="mt-8 text-xs text-ink-400">
          <Link to="/" className="hover:underline">Back to sign in</Link>
        </p>
      </main>
    </div>
  );
}

function RequestLink() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState("idle"); // idle | busy | sent | error
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    const value = email.trim();
    if (!value) return;
    setState("busy");
    setError(null);
    try {
      await api.requestPasswordReset(value);
      setState("sent");
    } catch (err) {
      setState("error");
      setError(
        err.status === 422
          ? "That does not look like an email address."
          : err.status === 429
            ? "Too many attempts. Please wait a minute and try again."
            : `Could not send a link right now: ${err.message}`,
      );
    }
  }

  if (state === "sent") {
    return (
      <p className="mt-4 text-sm text-ink-600" role="status">
        If {email.trim()} has a Pulse account, a link to reset its password is on its way. It
        works once and expires; check your spam folder if it has not arrived in a few minutes.
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="mt-6 space-y-3">
      <p className="text-sm text-ink-600">
        Enter the address you sign in with and we will email you a link to choose a new password.
      </p>
      <label className="label" htmlFor="reset-email">
        Email
      </label>
      <input
        id="reset-email"
        className="input"
        type="email"
        required
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        aria-invalid={state === "error" || undefined}
        aria-describedby={error ? "reset-error" : undefined}
      />
      {error && (
        <p id="reset-error" className="text-sm text-bad" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="btn-primary" disabled={state === "busy" || !email.trim()}>
        {state === "busy" ? "Sending…" : "Email me a link"}
      </button>
    </form>
  );
}

function SetPassword({ token }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [state, setState] = useState("idle"); // idle | busy | done | error
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    if (password !== confirm) {
      setState("error");
      setError("The two passwords are not the same.");
      return;
    }
    setState("busy");
    setError(null);
    try {
      await api.confirmPasswordReset(token, password);
      setState("done");
    } catch (err) {
      setState("error");
      setError(
        err.status === 429 ? "Too many attempts. Please wait a minute and try again." : err.message,
      );
    }
  }

  if (state === "done") {
    return (
      <p className="mt-4 text-sm text-ink-600" role="status">
        Your password has been changed, and you have been signed out everywhere else.{" "}
        <Link to="/" className="text-brand-600 hover:underline">
          Sign in with the new one
        </Link>
        .
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="mt-6 space-y-3">
      <label className="label" htmlFor="reset-password">
        New password
      </label>
      <input
        id="reset-password"
        className="input"
        type="password"
        required
        minLength={8}
        maxLength={128}
        autoComplete="new-password"
        placeholder="At least 8 characters"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <label className="label" htmlFor="reset-confirm">
        The same again
      </label>
      <input
        id="reset-confirm"
        className="input"
        type="password"
        required
        minLength={8}
        maxLength={128}
        autoComplete="new-password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        aria-invalid={state === "error" || undefined}
        aria-describedby={error ? "reset-error" : undefined}
      />
      {error && (
        <p id="reset-error" className="text-sm text-bad" role="alert">
          {error}{" "}
          {/expired|used|invalid/i.test(error) && (
            <Link to="/reset-password" reloadDocument className="text-brand-600 hover:underline">
              Ask for a new link.
            </Link>
          )}
        </p>
      )}
      <button type="submit" className="btn-primary" disabled={state === "busy"}>
        {state === "busy" ? "Saving…" : "Set new password"}
      </button>
    </form>
  );
}
