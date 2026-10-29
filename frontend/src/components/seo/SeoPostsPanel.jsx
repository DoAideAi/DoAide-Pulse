import { cloneElement, isValidElement, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import {
  insertLink,
  metaLengthHint,
  parseKeywords,
  postLabel,
  postTone,
  toneClass,
} from "../../lib/seo";
import { ErrorBanner, SectionHeader, Skeleton } from "../ui/Bits";

/** How long the editor waits after typing stops before asking for links. */
export const LINK_DEBOUNCE_MS = 600;

const EMPTY = {
  projectId: "",
  title: "",
  meta: "",
  focus: "",
  keywords: "",
  body: "",
  when: "optimal",
  at: "",
};

/**
 * Write an SEO post and put it on the calendar in one go.
 *
 * Not a second editor: the post is an ordinary piece tagged `seo`, created and
 * scheduled through the same endpoints as everything else, so the preflight,
 * the cadence-driven slot picker and the publishers all apply. Editing after
 * the fact happens in the full editor, linked from the queue.
 */
export default function SeoPostsPanel() {
  const projects = useApi(() => api.listProjects(), []);
  const platforms = useApi(() => api.platforms(), []);
  const posts = useApi(() => api.seoPosts(), []);

  const [form, setForm] = useState(EMPTY);
  const [targets, setTargets] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const keywords = useMemo(() => parseKeywords(form.keywords), [form.keywords]);
  const meta = metaLengthHint(form.meta);

  const connected = useMemo(
    () => (platforms.data || []).filter((p) => p.connection?.status === "connected"),
    [platforms.data],
  );
  const chosen = targets ?? connected.map((p) => p.platform);

  const projectId = form.projectId || String(projects.data?.[0]?.id ?? "");

  const links = useLinkSuggestions(form, keywords);
  const slots = useApi(
    () => (chosen.length ? api.seoOptimalSlots(chosen) : Promise.resolve([])),
    [chosen.join(",")],
  );

  function toggle(platform) {
    setTargets(chosen.includes(platform) ? chosen.filter((p) => p !== platform) : [...chosen, platform]);
  }

  async function save(e) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    if (form.when !== "draft" && chosen.length === 0) {
      setError("Pick at least one platform to publish to, or save it as a draft.");
      return;
    }
    if (form.when === "custom" && !form.at) {
      setError("Pick a date and time, or let Pulse choose one.");
      return;
    }
    setSaving(true);
    let created = null;
    try {
      created = await api.createContent({
        project_id: Number(projectId),
        content_type: "how_to",
        title: form.title.trim(),
        body_markdown: form.body,
        meta_description: form.meta.trim(),
        keywords,
        focus_keyword: form.focus.trim(),
        tags: ["seo"],
      });
      if (form.when !== "draft") {
        await api.scheduleContent(
          created.id,
          form.when === "optimal"
            ? { platforms: chosen, optimize: true }
            : { platforms: chosen, scheduled_for: new Date(form.at).toISOString() },
        );
      }
      setNotice(
        form.when === "draft" ? `Saved “${created.title}” as a draft.` : `Scheduled “${created.title}”.`,
      );
      setForm({ ...EMPTY, projectId: form.projectId });
      posts.reload();
    } catch (err) {
      const message = err.message || String(err);
      setError(created ? `Saved as a draft, but scheduling failed: ${message}` : message);
      if (created) posts.reload();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section aria-label="New SEO post" className="space-y-4">
        <SectionHeader
          title="New SEO post"
          subtitle="Written here, published through the normal pipeline at the best time for each platform."
        />
        <ErrorBanner message={error || projects.error} />
        {notice && (
          <p role="status" className="rounded-lg border border-good/25 bg-good-wash px-4 py-3 text-sm text-ink-700">
            {notice}
          </p>
        )}
        {projects.data && projects.data.length === 0 && (
          <p className="text-sm text-ink-500">
            Create a project first — every post belongs to one. <Link to="/projects" className="text-brand-600">Projects</Link>
          </p>
        )}
        <form className="panel space-y-5 px-5 py-5" onSubmit={save}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Project" id="seo-project">
              <select id="seo-project" className="input" value={projectId} onChange={set("projectId")} required>
                {(projects.data || []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Focus keyword" id="seo-focus">
              <input id="seo-focus" className="input" value={form.focus} onChange={set("focus")} placeholder="file itr online" />
            </Field>
          </div>
          <Field label="Title" id="seo-title">
            <input id="seo-title" className="input" value={form.title} onChange={set("title")} required maxLength={300} />
          </Field>
          <Field label="Meta description" id="seo-meta" hint={<span className={toneClass(meta.tone).split(" ").pop()}>{meta.hint}</span>}>
            <textarea id="seo-meta" className="input" rows={2} value={form.meta} onChange={set("meta")} maxLength={320} />
          </Field>
          <Field label="Target keywords" id="seo-keywords" hint="Comma separated.">
            <input id="seo-keywords" className="input" value={form.keywords} onChange={set("keywords")} placeholder="income tax, itr, form 16" />
          </Field>
          <Field label="Content (Markdown)" id="seo-body">
            <textarea id="seo-body" className="input font-mono" rows={14} value={form.body} onChange={set("body")} />
          </Field>

          <fieldset className="space-y-2">
            <legend className="label">Publish to</legend>
            {connected.length === 0 ? (
              <p className="text-sm text-ink-500">
                No platform is connected — it can still be saved as a draft.{" "}
                <Link to="/settings" className="text-brand-600">Connect one</Link>
              </p>
            ) : (
              <div className="flex flex-wrap gap-3">
                {connected.map((p) => (
                  <label key={p.platform} className="flex min-h-[48px] items-center gap-2 text-sm text-ink-700">
                    <input type="checkbox" checked={chosen.includes(p.platform)} onChange={() => toggle(p.platform)} />
                    {p.display_name}
                  </label>
                ))}
              </div>
            )}
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="label">When</legend>
            <div className="flex flex-wrap gap-4 text-sm text-ink-700">
              {[
                ["optimal", "Best time (Pulse picks)"],
                ["custom", "Pick a time"],
                ["draft", "Save as draft"],
              ].map(([value, label]) => (
                <label key={value} className="flex min-h-[48px] items-center gap-2">
                  <input type="radio" name="seo-when" value={value} checked={form.when === value} onChange={set("when")} />
                  {label}
                </label>
              ))}
            </div>
            {form.when === "optimal" && slots.data?.length > 0 && (
              <ul className="space-y-1 text-xs text-ink-500" aria-label="Suggested times">
                {slots.data.map((s) => (
                  <li key={s.platform}>
                    <span className="font-mono text-ink-700">{s.platform}</span> — {formatDateTime(s.when)}
                    {s.rationale && <span className="text-ink-400"> · {s.rationale}</span>}
                  </li>
                ))}
              </ul>
            )}
            {form.when === "custom" && (
              <input type="datetime-local" aria-label="Publish at" className="input max-w-xs" value={form.at} onChange={set("at")} />
            )}
          </fieldset>

          <button className="btn-primary" type="submit" disabled={saving || !projectId}>
            {saving ? "Saving…" : form.when === "draft" ? "Save draft" : "Schedule post"}
          </button>
        </form>
      </section>

      <aside className="space-y-8">
        <LinkSuggestions links={links} onInsert={(anchor, url) => setForm((f) => ({ ...f, body: insertLink(f.body, anchor, url) }))} />
        <Queue state={posts} />
      </aside>
    </div>
  );
}

/**
 * A labelled field, with its hint tied to the control by `aria-describedby`.
 *
 * The hint used to be a plain paragraph beside the input: read by anyone who
 * could see it, and announced to nobody using a screen reader — so the meta
 * description's "Google will cut it off" reached exactly the users who could
 * already see the colour change.
 */
function Field({ label, id, hint, children }) {
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div>
      <label className="label" htmlFor={id}>
        {label}
      </label>
      {hintId && isValidElement(children)
        ? cloneElement(children, { "aria-describedby": hintId })
        : children}
      {hint && (
        <p id={hintId} className="mt-1 text-xs text-ink-400">
          {hint}
        </p>
      )}
    </div>
  );
}

/** Ask for link ideas once typing pauses; keep the last answer while asking again. */
function useLinkSuggestions(form, keywords) {
  const [links, setLinks] = useState(null);
  const key = JSON.stringify([form.title, form.body, form.focus, keywords]);
  useEffect(() => {
    if (!form.title && !form.body && keywords.length === 0 && !form.focus) {
      setLinks(null);
      return undefined;
    }
    let live = true;
    const id = setTimeout(() => {
      api
        .seoLinkSuggestions({
          title: form.title,
          body_markdown: form.body,
          keywords,
          focus_keyword: form.focus,
        })
        .then((data) => live && setLinks(data))
        .catch(() => live && setLinks(null));
    }, LINK_DEBOUNCE_MS);
    return () => {
      live = false;
      clearTimeout(id);
    };
    // `key` stands for every input the request is built from.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return links;
}

function LinkSuggestions({ links, onInsert }) {
  const empty = !links || (links.products.length === 0 && links.posts.length === 0);
  return (
    <section aria-label="Internal link suggestions" className="panel px-5 py-4">
      <p className="eyebrow mb-2">Internal links</p>
      {empty ? (
        <p className="text-sm text-ink-500">
          Add keywords or a few paragraphs and Pulse suggests DoAide products and your own posts to link to.
        </p>
      ) : (
        <ul className="space-y-2 text-sm">
          {links.products.map((l) => (
            <li key={l.site_key} className="flex items-center justify-between gap-2">
              <span className="min-w-0">
                <span className="font-medium text-ink-900">{l.name}</span>{" "}
                <span className="text-xs text-ink-400">“{l.anchor}”</span>
              </span>
              <button type="button" className="btn-quiet" onClick={() => onInsert(l.anchor, l.url)} aria-label={`Link ${l.name}`}>
                Insert
              </button>
            </li>
          ))}
          {links.posts.map((l) => (
            <li key={l.content_id} className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate text-ink-700" title={l.matched_keywords.join(", ")}>
                {l.title}
              </span>
              {l.url && (
                <button
                  type="button"
                  className="btn-quiet"
                  onClick={() => onInsert(l.matched_keywords[0] || l.title, l.url)}
                  aria-label={`Link ${l.title}`}
                >
                  Insert
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Queue({ state }) {
  return (
    <section aria-label="SEO post queue">
      <SectionHeader title="Queue" subtitle="Posts tagged seo." />
      <ErrorBanner message={state.error} onRetry={state.reload} />
      {!state.data && state.loading && <Skeleton rows={3} />}
      {state.data?.length === 0 && <p className="text-sm text-ink-500">No SEO posts yet.</p>}
      {state.data?.length > 0 && (
        <ul className="panel divide-y divide-line">
          {state.data.map((p) => (
            <li key={p.id} className="space-y-1 px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <Link to={`/content/${p.id}`} className="min-w-0 text-sm font-medium text-ink-900 hover:text-brand-600">
                  {p.title}
                </Link>
                <span className={`badge ${toneClass(postTone(p))}`}>{postLabel(p)}</span>
              </div>
              <p className="text-xs text-ink-400">
                {p.focus_keyword && <span className="font-mono">{p.focus_keyword} · </span>}
                {p.scheduled_for && !p.published_at
                  ? formatDateTime(p.scheduled_for)
                  : p.published_at
                    ? formatDateTime(p.published_at)
                    : p.project_name}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
