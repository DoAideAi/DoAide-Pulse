/**
 * A deliberately small Markdown renderer for the content preview.
 *
 * Not a general-purpose parser — it handles what the generator actually
 * produces: ATX headings, fenced code, lists, blockquotes, bold/italic/inline
 * code, and links. Anything it does not recognise passes through as a
 * paragraph, which is the right failure for a preview.
 *
 * Why not a library: the preview is the only consumer, the input is our own
 * generated Markdown rather than arbitrary user HTML, and every candidate
 * (marked, markdown-it) is larger than the rest of this app's JS put together.
 *
 * Everything is escaped before any tag is emitted, so a post containing
 * `<script>` renders as text. The renderer never emits a tag it was not asked
 * for — there is no raw-HTML passthrough.
 */

/**
 * Control characters have no rendering here, and one of them has a job.
 *
 * The inline-code pass below lifts spans out behind a NUL-delimited
 * placeholder, on the stated grounds that a NUL "cannot survive escapeHtml from
 * real input". Escaping four punctuation characters does not remove a NUL, and
 * a body reaches this renderer from the API as well as from the textarea —
 * `body_markdown` is a JSON string, and JSON spells NUL `\u0000` quite happily.
 * So the placeholder's alphabet was shared with the document, and a body
 * carrying its own `NUL 0 NUL` rendered `<code>undefined</code>`, or, next to a
 * real code span, a second copy of that span's text.
 *
 * Never an injection — everything either side is escaped first, and this pass
 * emits nothing but `<code>` — but the preview it corrupts is a public page.
 * Dropping the characters makes the placeholder's alphabet private again, which
 * is what the comment below has always claimed it was. Newline and tab stay:
 * the renderer splits on the first and code blocks are indented with the second.
 */
const CONTROL_CHARS = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;

function escapeHtml(text) {
  return text
    .replace(CONTROL_CHARS, "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Inline spans, applied to already-escaped text.
 *
 * Inline code is lifted out into placeholders before the emphasis and link
 * passes run, then put back. Merely replacing it *first* would not be enough:
 * the later regexes still scan the whole string, so `` `a *b* c` `` would come
 * back with an <em> inside the <code>. The placeholder is a NUL, which
 * escapeHtml strips from the document first — see CONTROL_CHARS — so the
 * delimiter cannot appear in the text it delimits.
 */
const CODE_PLACEHOLDER = "\u0000";

function inline(text) {
  const codes = [];
  let out = text.replace(/`([^`]+)`/g, (_, code) => {
    codes.push(code);
    return `${CODE_PLACEHOLDER}${codes.length - 1}${CODE_PLACEHOLDER}`;
  });

  out = out
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    // Only http(s) links become anchors — a `javascript:` URL in generated
    // text should render as the text it is. The address may hold one level of
    // balanced parentheses: stopping at the first ")" cut every Wikipedia
    // link at "…Python_(programming_language" and left the ")" in the text.
    .replace(
      /\[([^\]]+)\]\((https?:\/\/(?:[^()\s]|\([^()\s]*\))+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
    );

  return out.replace(
    new RegExp(`${CODE_PLACEHOLDER}(\\d+)${CODE_PLACEHOLDER}`, "g"),
    (_, index) => `<code>${codes[Number(index)]}</code>`,
  );
}

export function renderMarkdown(markdown) {
  if (!markdown) return "";

  const lines = escapeHtml(markdown).split("\n");
  const out = [];
  let paragraph = [];
  let list = null; // "ul" | "ol" | null
  let fence = null; // the language, or "" — null when not in a fence

  const flushParagraph = () => {
    if (paragraph.length) {
      out.push(`<p>${inline(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      out.push(`</${list}>`);
      list = null;
    }
  };
  const flushAll = () => {
    flushParagraph();
    flushList();
  };

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");

    // ---- fenced code ----
    const fenceMatch = line.match(/^```(\w*)/);
    if (fenceMatch) {
      if (fence === null) {
        flushAll();
        fence = fenceMatch[1] || "";
        out.push(
          fence ? `<pre><code class="language-${fence}">` : "<pre><code>",
        );
      } else {
        out.push("</code></pre>");
        fence = null;
      }
      continue;
    }
    if (fence !== null) {
      // Inside a fence everything is literal, including what looks like syntax.
      out.push(`${line}\n`);
      continue;
    }

    if (!line.trim()) {
      flushAll();
      continue;
    }

    // ---- headings ----
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushAll();
      const level = Math.min(heading[1].length, 6);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }

    // ---- horizontal rule ----
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      flushAll();
      out.push("<hr />");
      continue;
    }

    // ---- blockquote ----
    // `&gt;`, not `>`: escapeHtml runs over the whole document before these
    // branches see a line, so by here every quote marker the author typed is
    // already an entity. Matching the raw character never fired, and quotes
    // fell through to a paragraph showing a literal `>`.
    const quote = line.match(/^&gt;\s?(.*)$/);
    if (quote) {
      flushAll();
      out.push(`<blockquote>${inline(quote[1])}</blockquote>`);
      continue;
    }

    // ---- lists ----
    const unordered = line.match(/^\s*[-*+]\s+(.*)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (unordered || ordered) {
      const wanted = unordered ? "ul" : "ol";
      flushParagraph();
      if (list !== wanted) {
        flushList();
        out.push(`<${wanted}>`);
        list = wanted;
      }
      out.push(`<li>${inline((unordered || ordered)[1])}</li>`);
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  if (fence !== null) out.push("</code></pre>");
  flushAll();
  return out.join("\n");
}
