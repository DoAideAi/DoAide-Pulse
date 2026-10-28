import { useState } from "react";
import { Link } from "react-router-dom";

export const DISMISS_KEY = "pulse.gettingStarted.dismissed";

/**
 * The first-run checklist: the four things between signing in and a post
 * that someone has actually read.
 *
 * Each step is read from data the dashboard already has rather than from a
 * "completed" flag of its own, so it can never claim a step the account has
 * not done — and it disappears on its own once everything is. Dismissing it
 * is remembered per browser; nothing about it is worth a server round-trip.
 * `fallback` renders in its place once it is hidden or finished.
 *
 * `connectedCount` is null while the destinations are still loading, and the
 * step reads as not done until they arrive rather than flickering to done.
 */
export function gettingStartedSteps({
  projectCount,
  connectedCount,
  contentCount,
  publishedCount,
}) {
  return [
    {
      key: "project",
      title: "Register a project",
      hint: "Its repo, audience and tone are what every draft is written from.",
      to: "/projects",
      cta: "Add project",
      done: projectCount > 0,
    },
    {
      key: "destination",
      title: "Connect a destination",
      hint: "Dev.to, Hashnode, Bluesky, your own blog repo — wherever posts should land.",
      to: "/settings",
      cta: "Connect",
      done: (connectedCount ?? 0) > 0,
    },
    {
      key: "draft",
      title: "Generate your first draft",
      hint: "Pick a project and a content type; Pulse writes from your real commits.",
      to: "/content",
      cta: "Generate",
      done: contentCount > 0,
    },
    {
      key: "publish",
      title: "Publish it",
      // To the drafts, not /publish: that page is the queue of what is already
      // on its way, so a first-time user arrived at "Nothing queued" and had to
      // find their way back to the piece. Publishing happens in the editor.
      hint: "Open the draft and press Publish — send it now or pick a time.",
      to: "/content",
      cta: "Open drafts",
      done: publishedCount > 0,
    },
  ];
}

function readDismissed() {
  try {
    return window.localStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

export default function GettingStarted({ fallback = null, ...props }) {
  const [dismissed, setDismissed] = useState(readDismissed);
  const steps = gettingStartedSteps(props);
  const doneCount = steps.filter((step) => step.done).length;

  if (dismissed || doneCount === steps.length) return fallback;

  const next = steps.find((step) => !step.done);

  function dismiss() {
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // Private mode: it just comes back next visit.
    }
    setDismissed(true);
  }

  return (
    <section className="panel p-5" aria-labelledby="getting-started-title">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="getting-started-title" className="text-base font-semibold text-ink-900">
            Get your first post out
          </h2>
          <p className="mt-0.5 text-xs text-ink-400">
            {doneCount} of {steps.length} done
          </p>
        </div>
        <button className="btn-quiet -mr-2.5 -mt-2" onClick={dismiss}>
          Hide
        </button>
      </div>

      <div
        className="mt-3 h-1.5 rounded-full bg-ink-400/15"
        role="progressbar"
        aria-valuenow={doneCount}
        aria-valuemin={0}
        aria-valuemax={steps.length}
        aria-label="Setup progress"
      >
        <div
          className="h-full rounded-full bg-brand-500 transition-all"
          style={{ width: `${(doneCount / steps.length) * 100}%` }}
        />
      </div>

      <ol className="mt-4 space-y-2">
        {steps.map((step, index) => (
          <li
            key={step.key}
            data-testid={`step-${step.key}`}
            data-done={step.done ? "true" : "false"}
            className={`flex flex-col gap-3 rounded-lg px-3 py-3 sm:flex-row sm:items-center ${
              step === next ? "bg-brand-50" : ""
            }`}
          >
            <span className="flex min-w-0 flex-1 items-start gap-3">
              <span
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[11px] ${
                  step.done ? "bg-good text-canvas" : "border border-line-strong text-ink-500"
                }`}
                aria-hidden="true"
              >
                {step.done ? "✓" : index + 1}
              </span>
              <span className="min-w-0">
                <span
                  className={`block text-sm font-medium ${
                    step.done ? "text-ink-400 line-through" : "text-ink-900"
                  }`}
                >
                  {step.title}
                  {step.done && <span className="sr-only"> (done)</span>}
                </span>
                {!step.done && (
                  <span className="mt-0.5 block text-xs text-ink-500">{step.hint}</span>
                )}
              </span>
            </span>
            {!step.done && (
              <Link
                to={step.to}
                className={`${step === next ? "btn-primary" : "btn-ghost"} w-full shrink-0 sm:w-auto`}
              >
                {step.cta}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
