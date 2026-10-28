import { useState } from "react";
import { Link } from "react-router-dom";
import PublicNav from "../components/PublicNav";
import { api } from "../lib/api";
import { usePageMeta } from "../lib/pageMeta";

/**
 * Take an address off the newsletter list.
 *
 * The API deletes the address and answers the same whether or not it was on
 * the list, so the confirmation here does not say "we found you" either — it
 * says the address is not on the list any more, which is true either way.
 */
export default function Unsubscribe() {
  usePageMeta({ title: "Unsubscribe | DoAide Pulse", path: "/unsubscribe" });
  const [email, setEmail] = useState("");
  const [state, setState] = useState("idle"); // idle | busy | done | error
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    const value = email.trim();
    if (!value) return;
    setState("busy");
    setError(null);
    try {
      await api.unsubscribe(value);
      setState("done");
    } catch (err) {
      setState("error");
      setError(
        err.status === 422
          ? "That does not look like an email address."
          : err.status === 429
            ? "Too many attempts. Please wait a minute and try again."
            : `Could not unsubscribe right now: ${err.message}`,
      );
    }
  }

  return (
    <div className="min-h-screen bg-canvas text-ink-700">
      <PublicNav />
      <main id="main" tabIndex={-1} className="mx-auto max-w-md px-4 py-16">
        <h1 className="font-display text-3xl text-ink-900">Unsubscribe</h1>
        {state === "done" ? (
          <p className="mt-4 text-sm text-ink-600" role="status">
            {email.trim()} is not on the list any more. Its record has been deleted.
          </p>
        ) : (
          <form onSubmit={submit} className="mt-6 space-y-3">
            <p className="text-sm text-ink-600">
              Enter the address you subscribed with. It is deleted, not just marked.
            </p>
            <label className="label" htmlFor="unsubscribe-email">
              Email
            </label>
            <input
              id="unsubscribe-email"
              className="input"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={state === "error" || undefined}
              aria-describedby={error ? "unsubscribe-error" : undefined}
            />
            {error && (
              <p id="unsubscribe-error" className="text-sm text-bad" role="alert">
                {error}
              </p>
            )}
            <button type="submit" className="btn-primary" disabled={state === "busy" || !email.trim()}>
              {state === "busy" ? "Unsubscribing…" : "Unsubscribe"}
            </button>
          </form>
        )}
        <p className="mt-8 text-xs text-ink-400">
          <Link to="/" className="hover:underline">Back to DoAide Pulse</Link>
        </p>
      </main>
    </div>
  );
}
