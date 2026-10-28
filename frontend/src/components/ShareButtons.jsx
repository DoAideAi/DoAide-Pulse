import { useState } from "react";
import trackEvent from "../lib/trackEvent";

export default function ShareButtons({ url, title = "", text = "Check this out!", variant = "default" }) {
  // null, "ok" or "failed".
  const [copied, setCopied] = useState(null);
  const shareUrl =
    url || (typeof window !== "undefined" ? window.location.href : "");
  const encoded = encodeURIComponent(shareUrl);

  const whatsappText = title
    ? encodeURIComponent(`\u{1F4F0} ${title} — Read now → ${shareUrl} | Published with DoAide Pulse`)
    : encodeURIComponent(`${text} ${shareUrl}`);

  const tweetText = title
    ? encodeURIComponent(title)
    : encodeURIComponent(text);

  const linkedInUrl = `https://www.linkedin.com/sharing/share-offsite/?url=${encoded}`;

  function copyLink() {
    // `navigator.clipboard` is missing outright on plain http and in some
    // in-app browsers, and refused by others; the button used to do nothing
    // visible in either case. Every other copy button in the app says so.
    Promise.resolve()
      .then(() => navigator.clipboard.writeText(shareUrl))
      .then(
        () => {
          setCopied("ok");
          trackEvent("share", { platform: "copy-link" });
        },
        () => setCopied("failed"),
      )
      .finally(() => setTimeout(() => setCopied(null), 4000));
  }

  const btnClass = variant === "prominent"
    ? "inline-flex min-h-[48px] items-center gap-1.5 rounded-lg border border-line bg-paper px-4 py-2 text-sm font-medium text-ink-700 transition hover:border-brand-500 hover:text-brand-500"
    : "btn-ghost !px-3 !text-xs";

  return (
    <div className="flex flex-wrap gap-3" role="group" aria-label="Share this article">
      <a
        href={`https://wa.me/?text=${whatsappText}`}
        target="_blank"
        rel="noopener noreferrer"
        className={btnClass}
        data-testid="share-whatsapp"
        onClick={() => trackEvent("share", { platform: "whatsapp" })}
      >
        WhatsApp
      </a>
      <a
        href={`https://twitter.com/intent/tweet?text=${tweetText}&url=${encoded}`}
        target="_blank"
        rel="noopener noreferrer"
        className={btnClass}
        data-testid="share-twitter"
        onClick={() => trackEvent("share", { platform: "twitter" })}
      >
        Twitter / X
      </a>
      <a
        href={linkedInUrl}
        target="_blank"
        rel="noopener noreferrer"
        className={btnClass}
        data-testid="share-linkedin"
        onClick={() => trackEvent("share", { platform: "linkedin" })}
      >
        LinkedIn
      </a>
      <button type="button" onClick={copyLink} className={btnClass} data-testid="share-copy">
        {copied === "ok" ? "Copied!" : copied === "failed" ? "Couldn't copy" : "Copy link"}
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {copied === "ok" && "Link copied to the clipboard."}
        {copied === "failed" && `Your browser blocked copying. The link is ${shareUrl}`}
      </span>
    </div>
  );
}
