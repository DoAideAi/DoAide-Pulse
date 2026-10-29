import { Suspense, lazy, useState } from "react";
import { useLocation } from "react-router-dom";
import { loadWithReload } from "../lib/lazyPage";

const loadForm = () => import("./FeedbackForm");
// Through ``loadWithReload`` like every page: a tab opened before a deploy
// asks for the old chunk name, which the deploy deleted, and plain ``lazy``
// sent that straight to an error boundary.
const FeedbackForm = lazy(() => loadWithReload(loadForm));
// A warm-up on hover or focus. Its failure is not worth a word — the real load
// recovers — but uncaught it was an unhandled rejection in the console.
const prefetchForm = () => loadForm().catch(() => {});

/**
 * Pages that are not Pulse's own UI: the subscribe widget runs inside other
 * people's sites, and a preview link is someone else's draft shown to a
 * reader. A feedback button on either would be addressed to the wrong people.
 */
const HIDDEN_ON = [/^\/embed/, /^\/preview\//];

/**
 * The floating "Feedback" button and the form it opens.
 *
 * The feature area is detected from the route the moment the form opens and
 * shown to the person as a choice they can change — "Feedback about: Content
 * Editor" — because a guess the user cannot see or correct is a guess the
 * feedback list then has to be suspicious of.
 */
export default function FeedbackWidget() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);

  if (HIDDEN_ON.some((pattern) => pattern.test(pathname))) return null;

  return (
    <>
      {/* z-30, under Dialog's z-40 backdrop: at the same z-index and later in
          the DOM it floated over every other open modal, still clickable, and
          opened a second dialog on top of the first. Icon-only below `sm`, so
          it clears the dashboard's centred Quick Actions bar on a phone. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        // Fetched when the pointer or focus arrives, so it is usually there by
        // the click; the click itself loads it otherwise.
        onPointerEnter={prefetchForm}
        onFocus={prefetchForm}
        className="fixed bottom-5 right-4 z-30 inline-flex h-11 min-w-11 items-center justify-center gap-2 rounded-full px-3 text-sm font-semibold text-white shadow-lg hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 sm:right-5 sm:px-4 print:hidden"
        style={{ backgroundColor: "#2563eb" }}
        aria-haspopup="dialog"
        aria-label="Feedback"
      >
        <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
          <path d="M3 4.5A2.5 2.5 0 0 1 5.5 2h9A2.5 2.5 0 0 1 17 4.5v6a2.5 2.5 0 0 1-2.5 2.5H9.4l-3.6 3.1A.5.5 0 0 1 5 15.7V13h.5A2.5 2.5 0 0 1 3 10.5v-6Z" />
        </svg>
        <span className="hidden sm:inline">Feedback</span>
      </button>
      {open && (
        <Suspense fallback={null}>
          <FeedbackForm pathname={pathname} onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </>
  );
}
