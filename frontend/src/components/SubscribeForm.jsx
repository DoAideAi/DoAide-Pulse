import { useRef, useState } from "react";
import { api } from "../lib/api";
import trackEvent from "../lib/trackEvent";

/**
 * Newsletter sign-up for public pages, posting to the same endpoint as the
 * embed widget. `source` is recorded with the subscriber, so the analytics
 * panel can tell an article sign-up from a widget one.
 */
export default function SubscribeForm({ source = "article", heading = "Get the next one by email" }) {
  const [email, setEmail] = useState("");
  // idle | busy | done | error
  const [state, setState] = useState("idle");
  const [message, setMessage] = useState("");
  const inputRef = useRef(null);

  async function submit(event) {
    event.preventDefault();
    const value = email.trim();
    if (!value) {
      setState("error");
      setMessage("Enter your email address.");
      inputRef.current?.focus();
      return;
    }
    setState("busy");
    setMessage("");
    try {
      await api.subscribe(value, source);
      setState("done");
      setMessage("You're subscribed. Thanks for reading!");
      setEmail("");
      trackEvent("subscribe", { source });
    } catch (err) {
      setState("error");
      setMessage(
        err.status === 422
          ? "That doesn't look like an email address."
          : err.status === 429
            ? "Too many attempts — try again in a minute."
            : "Couldn't subscribe right now. Please try again.",
      );
      inputRef.current?.focus();
    }
  }

  const invalid = state === "error";

  return (
    <div className="panel p-6">
      <p id={`${source}-subscribe-heading`} className="mb-3 text-sm font-medium text-ink-900">
        {heading}
      </p>
      {state !== "done" && (
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={submit}
          noValidate
          aria-labelledby={`${source}-subscribe-heading`}
        >
          <label htmlFor={`${source}-subscribe-email`} className="sr-only">
            Email address
          </label>
          <input
            ref={inputRef}
            id={`${source}-subscribe-email`}
            type="email"
            autoComplete="email"
            className="input flex-1"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={invalid}
            aria-describedby={`${source}-subscribe-status`}
            // readOnly, not disabled: a disabled field drops focus, and the
            // failure path puts focus back here for the reader to correct.
            readOnly={state === "busy"}
          />
          <button type="submit" className="btn-primary" disabled={state === "busy"}>
            {state === "busy" ? "Subscribing…" : "Subscribe"}
          </button>
        </form>
      )}
      <p
        id={`${source}-subscribe-status`}
        role="status"
        aria-live="polite"
        className={`mt-2 text-xs ${invalid ? "text-bad" : "text-ink-500"} ${message ? "" : "sr-only"}`}
      >
        {message}
      </p>
    </div>
  );
}
