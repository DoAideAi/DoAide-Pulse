import { useState } from "react";
import { api } from "../lib/api";
import { FEATURE_AREAS, describeBrowser, featureFor } from "../lib/featureArea";
import Dialog from "./ui/Dialog";

const CATEGORIES = [
  { value: "bug", label: "Bug Report" },
  { value: "feature", label: "Feature Request" },
  { value: "general", label: "General Feedback" },
  { value: "other", label: "Other" },
];

/**
 * The form the Feedback button opens. Its own module, loaded on first open
 * (see FeedbackWidget), so it and Dialog stay out of the entry chunk every
 * page — the landing page included — downloads before anything else.
 */
export default function FeedbackForm({ pathname, onClose }) {
  const [feature, setFeature] = useState(() => featureFor(pathname));
  const [category, setCategory] = useState("general");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);

  const browser = describeBrowser(typeof navigator === "undefined" ? "" : navigator.userAgent);

  async function submit(event) {
    event.preventDefault();
    if (!message.trim()) {
      setError("Write something before sending.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.submitFeedback({
        category,
        message: message.trim(),
        email: email.trim() || null,
        // The path only; the server drops anything after it as well.
        page_url: pathname,
        detected_feature: feature,
      });
      setSent(true);
    } catch (err) {
      setError(
        err.status === 429
          ? "That is a lot of feedback in one hour — thank you. Please try again later."
          : `Could not send your feedback: ${err.message}`,
      );
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <Dialog label="Feedback sent" onClose={onClose} width="md">
        <h2 className="font-display text-2xl text-ink-900">Thank you</h2>
        <p className="text-sm text-ink-600" role="status">
          Your feedback about {feature} has been sent.
          {email.trim() ? " We will reply by email if we need more detail." : ""}
        </p>
        <div className="flex justify-end pt-2">
          <button type="button" className="btn-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog label="Send feedback" onClose={onClose} closable={!busy} onSubmit={submit} width="md">
      <h2 className="font-display text-2xl text-ink-900">Send feedback</h2>

      <div>
        <label className="label" htmlFor="fb-feature">
          Feedback about
        </label>
        <select
          id="fb-feature"
          className="input"
          value={feature}
          onChange={(e) => setFeature(e.target.value)}
        >
          {FEATURE_AREAS.map((area) => (
            <option key={area} value={area}>
              {area}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-ink-400">
          Detected from the page you are on — change it if it is about something else.
        </p>
      </div>

      <div>
        <label className="label" htmlFor="fb-category">
          Category
        </label>
        <select
          id="fb-category"
          className="input"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="label" htmlFor="fb-message">
          Your feedback
        </label>
        <textarea
          id="fb-message"
          className="input min-h-[7rem]"
          required
          maxLength={5000}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="What happened, or what would make this better?"
        />
      </div>

      <div>
        <label className="label" htmlFor="fb-email">
          Email <span className="normal-case tracking-normal">(optional, if you would like a reply)</span>
        </label>
        <input
          id="fb-email"
          className="input"
          type="email"
          maxLength={320}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>

      <p className="text-xs text-ink-400">
        Sent with this feedback: the page <span className="font-mono">{pathname}</span> and your
        browser ({browser}).
      </p>

      {error && (
        <p className="text-sm text-bad" role="alert">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn-primary"
          disabled={busy || !message.trim()}
          style={{ backgroundColor: "#2563eb" }}
        >
          {busy ? "Sending…" : "Send feedback"}
        </button>
      </div>
    </Dialog>
  );
}
