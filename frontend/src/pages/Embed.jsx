import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PublicNav from "../components/PublicNav";
import { usePageMeta } from "../lib/pageMeta";
import { PUBLIC_ROUTE_META } from "../data/publicRouteMeta";

const HEX = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i;

/** `#RRGGBB` for a valid hex, or `null` — the same rule embed.js applies. */
export function normalizeHex(value) {
  const m = HEX.exec((value || "").trim());
  if (!m) return null;
  const hex =
    m[1].length === 3
      ? m[1]
          .split("")
          .map((c) => c + c)
          .join("")
      : m[1];
  return `#${hex.toUpperCase()}`;
}

/** Button text that stays readable on *hex*, matching embed.js. */
export function textOn(hex) {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.179 ? "#0A0A0B" : "#FFFFFF";
}

/** An HTML attribute value, so a name like `Tom's "Weekly"` cannot end the
 * attribute early and leave the pasted snippet broken on the user's site. */
function attr(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function embedCode({ origin, name, color, layout, source }) {
  const attrs = [
    "data-pulse-signup",
    `data-name="${attr(name.trim() || "Newsletter")}"`,
    `data-color="${color}"`,
  ];
  if (layout === "full") attrs.push('data-layout="full"');
  if (source.trim()) attrs.push(`data-source="${attr(source.trim())}"`);
  return `<div ${attrs.join(" ")}></div>\n<script src="${origin}/embed.js" async></script>`;
}

export default function Embed() {
  const [name, setName] = useState("My Newsletter");
  const [color, setColor] = useState("#0D9488");
  // The text box keeps what was typed; only a valid hex reaches the preview,
  // the picker and the snippet. Before, a half-typed "#0D9" went straight into
  // all three and the snippet carried a colour the widget could not use.
  const [colorText, setColorText] = useState("#0D9488");
  const [layout, setLayout] = useState("compact");
  const [source, setSource] = useState("");
  const [copied, setCopied] = useState(null);
  const colorInvalid = normalizeHex(colorText) === null;

  usePageMeta(PUBLIC_ROUTE_META["/embed"]);

  const origin =
    typeof window !== "undefined"
      ? window.location.origin
      : "https://pulse.doaide.com";

  const code = embedCode({ origin, name, color, layout, source });
  // A "Copied" left over from an earlier version of the snippet would claim
  // the clipboard holds what is on screen now.
  useEffect(() => setCopied(null), [code]);
  const buttonText = textOn(color);

  function onColorText(value) {
    setColorText(value);
    const hex = normalizeHex(value);
    if (hex) setColor(hex);
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied("ok");
    } catch {
      // Clipboard access is refused on plain http and in some embedded
      // browsers. Say so, and leave the code selected for a manual copy.
      setCopied("failed");
      document.getElementById("code")?.select();
    }
  }

  return (
    <>
      <PublicNav />
      <div className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="page-title mb-2">Embed Widget Generator</h1>
        <p className="mb-6 text-ink-500">
          Add a newsletter signup form to your website with two lines of code.
        </p>

        <div className="panel p-5 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="wn" className="label">
                Newsletter name
              </label>
              <input
                id="wn"
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="wc" className="label">
                Accent color
              </label>
              <div className="flex gap-2">
                <input
                  id="wc"
                  type="color"
                  value={color}
                  onChange={(e) => {
                    const hex = normalizeHex(e.target.value);
                    setColor(hex);
                    setColorText(hex);
                  }}
                  className="h-10 w-10 cursor-pointer rounded border border-line"
                />
                <input
                  className="input flex-1"
                  value={colorText}
                  onChange={(e) => onColorText(e.target.value)}
                  aria-label="Color hex"
                  aria-invalid={colorInvalid}
                  aria-describedby={colorInvalid ? "wc-error" : undefined}
                  spellCheck={false}
                />
              </div>
              {colorInvalid && (
                <p id="wc-error" className="mt-1 text-xs text-bad">
                  Use a hex colour like #0D9488. The widget keeps {color} until then.
                </p>
              )}
            </div>
          </div>
          <div>
            <label htmlFor="wl" className="label">
              Layout
            </label>
            <select
              id="wl"
              className="input"
              value={layout}
              onChange={(e) => setLayout(e.target.value)}
            >
              <option value="compact">Compact</option>
              <option value="full">Full</option>
            </select>
          </div>
          <div>
            <label htmlFor="ws" className="label">
              Source tag <span className="font-normal text-ink-500">(optional)</span>
            </label>
            <input
              id="ws"
              className="input"
              value={source}
              placeholder="e.g. blog-footer"
              aria-describedby="ws-hint"
              onChange={(e) => setSource(e.target.value)}
            />
            <p id="ws-hint" className="mt-1 text-xs text-ink-500">
              Recorded with each signup, so you can tell which page brought them in.
            </p>
          </div>
        </div>

        <div className="mt-6">
          <h2 className="mb-2 text-sm font-semibold text-ink-900">Preview</h2>
          <div
            className="panel p-5"
            style={{ borderColor: color }}
            data-testid="embed-preview"
          >
            <p className="mb-3 font-semibold text-ink-900">
              Subscribe to {name.trim() || "Newsletter"}
            </p>
            {layout === "full" && (
              <p className="mb-3 text-sm text-ink-500">
                Get the latest insights delivered to your inbox.
              </p>
            )}
            <div className="flex gap-2">
              <input
                className="input flex-1"
                placeholder="you@example.com"
                aria-label="Email address (preview)"
                disabled
              />
              <button
                type="button"
                className="btn text-sm"
                style={{ backgroundColor: color, color: buttonText }}
                disabled
              >
                Subscribe
              </button>
            </div>
          </div>
        </div>

        <div className="mt-6">
          <div className="mb-1 flex items-center justify-between gap-3">
            <label htmlFor="code" className="label !mb-0">
              Embed code
            </label>
            <button type="button" className="btn-ghost !px-3 !text-xs" onClick={copy}>
              {copied === "ok" ? "Copied" : "Copy code"}
            </button>
          </div>
          <textarea
            id="code"
            readOnly
            rows={3}
            className="input font-mono text-xs"
            value={code}
            onFocus={(e) => e.target.select()}
          />
          <p role="status" aria-live="polite" className="mt-1 min-h-[1rem] text-xs text-ink-500">
            {copied === "ok" && "Copied to the clipboard. Paste it where the form should appear."}
            {copied === "failed" &&
              "Your browser blocked clipboard access — the code is selected, press Ctrl+C (⌘C) to copy it."}
          </p>
        </div>

        <div className="panel mt-10 p-5 text-center">
          <p className="mb-3 text-ink-900">
            Grow your subscriber list with DoAide Pulse.
          </p>
          <Link to="/" className="btn-primary">
            Get started free
          </Link>
        </div>
      </div>
    </>
  );
}
