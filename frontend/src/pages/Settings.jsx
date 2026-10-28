import { useState } from "react";
import { ErrorBanner, SectionHeader, Skeleton, Empty } from "../components/ui/Bits";
import Dialog from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { api } from "../lib/api";
import { formatWhen, titleize } from "../lib/format";
import { groupPlatforms, guideFor } from "../lib/platformGuides";

/**
 * Platform connections and service health.
 *
 * Credentials only ever travel inbound — the API never returns them, so a
 * connected platform shows a handle and a status, and re-connecting means
 * re-entering the key. That is deliberate, and the copy says so.
 */
export default function Settings() {
  const { user, refresh } = useAuth();
  const { data, error, loading, reload } = useApi(() => api.platforms(), []);
  const health = useApi(() => api.healthDetail(), []);
  const [connecting, setConnecting] = useState(null);
  const groups = groupPlatforms(data);

  function changed() {
    reload();
    refresh();
  }

  return (
    <div className="stagger space-y-8">
      <div>
        <h1 className="page-title">Settings</h1>
        <p className="mt-1 text-sm text-ink-500">
          Signed in as <span className="font-mono text-xs">{user?.email}</span>
        </p>
      </div>

      <ErrorBanner message={error} onRetry={reload} />

      <section aria-labelledby="accounts-heading">
        <div className="mb-4">
          <h2 id="accounts-heading" className="text-base font-semibold text-ink-900">
            Publishing accounts
          </h2>
          <p className="mt-0.5 text-sm text-ink-500">
            Connect the sites Pulse publishes to. Each one takes about a minute —
            keys are checked before saving, encrypted at rest and never sent back.
          </p>
        </div>

        {loading && !data ? (
          <Skeleton rows={4} />
        ) : (
          <div className="space-y-6">
            <SetupProgress groups={groups} />

            {groups.connected.length > 0 && (
              <div>
                <h3 className="label mb-2">Your accounts</h3>
                <div className="space-y-3">
                  {groups.connected.map((platform) => (
                    <PlatformRow
                      key={platform.platform}
                      platform={platform}
                      onConnect={() => setConnecting(platform)}
                      onChanged={changed}
                    />
                  ))}
                </div>
              </div>
            )}

            {groups.available.length > 0 && (
              <div>
                <h3 className="label mb-2">Add an account</h3>
                <ul className="grid gap-3 sm:grid-cols-2">
                  {groups.available.map((platform) => (
                    <AddPlatformCard
                      key={platform.platform}
                      platform={platform}
                      onConnect={() => setConnecting(platform)}
                    />
                  ))}
                </ul>
              </div>
            )}

            {groups.comingSoon.length > 0 && (
              <div>
                <h3 className="label mb-2">Coming soon</h3>
                <ul className="flex flex-wrap gap-1.5">
                  {groups.comingSoon.map((platform) => (
                    <li
                      key={platform.platform}
                      className="chip"
                      title={platform.caveat || "This adapter is not finished yet"}
                    >
                      {platform.display_name}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      <LlmKeySection />

      <details className="group border-t border-line pt-6">
        <summary className="cursor-pointer list-none">
          <h2 className="inline text-base font-semibold text-ink-900">Advanced</h2>
          <span className="ml-2 text-sm text-ink-500 group-open:hidden">Show</span>
          <p className="mt-0.5 text-sm text-ink-500">
            Webhooks, API keys and server status — for developers and operators.
            You don't need any of this to publish.
          </p>
        </summary>
        <div className="mt-6 space-y-8">
      <WebhooksSection />
      <ApiKeysSection />

      <section>
        <SectionHeader
          title="Service health"
          subtitle="What is configured on the server."
        />
        {health.loading && !health.data ? (
          <Skeleton rows={1} />
        ) : health.error && !health.data ? (
          // Without this a failed read rendered every row from ``undefined``:
          // "AI providers: none", "Credential encryption: off", each marked as
          // failing — a broken install reported by a page that only failed to
          // ask.
          <ErrorBanner
            message={`Could not check service health: ${health.error}`}
            onRetry={health.reload}
          />
        ) : (
          <dl className="panel divide-y divide-line">
            <HealthRow
              label="AI providers"
              value={
                health.data?.llm_providers?.length
                  ? health.data.llm_providers.join(" → ")
                  : "none configured"
              }
              ok={Boolean(health.data?.llm_providers?.length)}
              hint={
                health.data?.llm_providers?.length
                  ? "Tried in order; failing ones skipped for 5 min."
                  : "Set OPENROUTER_API_KEY for AI generation."
              }
            />
            <HealthRow
              label="GitHub"
              value={health.data?.github_configured ? "token set" : "anonymous"}
              ok={Boolean(health.data?.github_configured)}
              hint={
                health.data?.github_configured
                  ? "5000 req/hr."
                  : "60 req/hr, public only. Set GITHUB_TOKEN."
              }
            />
            <HealthRow
              label="Credential encryption"
              value={health.data?.credential_encryption ? "on" : "off"}
              ok={Boolean(health.data?.credential_encryption)}
              hint={
                health.data?.credential_encryption
                  ? "Tokens encrypted at rest."
                  : "Set TOKEN_ENCRYPTION_KEY for production."
              }
            />
            {Object.keys(health.data?.llm_breakers_open ?? {}).length > 0 && (
              <HealthRow
                label="Tripped providers"
                value={Object.keys(health.data.llm_breakers_open).join(", ")}
                ok={false}
                hint="These are being skipped until their cool-down expires."
              />
            )}
          </dl>
        )}
      </section>
        </div>
      </details>

      {connecting && (
        <ConnectDialog
          platform={connecting}
          onClose={() => setConnecting(null)}
          onDone={() => {
            setConnecting(null);
            changed();
          }}
        />
      )}

      <ExportAccountSection />
      <DeleteAccountSection />
    </div>
  );
}

/**
 * How far through setup this account is, in one line and one bar.
 *
 * The count leaves out connections the platform has stopped accepting — a
 * broken key is not a connected account — and says how many there are.
 */
function SetupProgress({ groups }) {
  const { total, healthy, attention, connected } = groups;
  if (total === 0) return null;
  const percent = Math.round((healthy / total) * 100);

  let message;
  if (connected.length === 0) {
    message = "No accounts yet. Pick a site below — Dev.to and Bluesky are the quickest to set up.";
  } else if (attention.length > 0) {
    message = `${attention.length} ${attention.length === 1 ? "account needs" : "accounts need"} a new key — see below.`;
  } else if (healthy === total) {
    message = "Every available site is connected.";
  } else {
    message = "Add more sites to reach more readers with each piece.";
  }

  return (
    <div className="panel p-5" data-testid="setup-progress">
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-sm font-semibold text-ink-900">
          {healthy} of {total} accounts connected
        </p>
        <span className="font-mono text-xs text-ink-400">{percent}%</span>
      </div>
      <div
        className="mt-3 h-1.5 overflow-hidden rounded-full bg-canvas"
        role="progressbar"
        aria-label="Accounts connected"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={healthy}
      >
        <div
          className="h-full rounded-full bg-brand-500 transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p
        className={`mt-2 text-xs ${attention.length > 0 ? "text-warn" : "text-ink-500"}`}
      >
        {message}
      </p>
    </div>
  );
}

/** One not-yet-connected site: what it is, and the one button that sets it up. */
function AddPlatformCard({ platform, onConnect }) {
  const guide = guideFor(platform);
  return (
    <li className="panel flex items-center justify-between gap-4 p-4">
      <div className="min-w-0">
        <h4 className="text-sm font-semibold text-ink-900">{platform.display_name}</h4>
        {guide.tagline && (
          <p className="mt-0.5 truncate text-xs text-ink-500">{guide.tagline}</p>
        )}
        {!platform.supports_metrics && (
          <p className="mt-0.5 text-[11px] text-ink-400">
            No stats API — views for this platform will stay empty.
          </p>
        )}
      </div>
      <button
        className="btn-primary shrink-0"
        onClick={onConnect}
        aria-label={`Connect ${platform.display_name}`}
      >
        Connect
      </button>
    </li>
  );
}

/* ---- Personal LLM key ---- */

/**
 * The user's own AI key. Optional: Pulse writes with the server's shared
 * providers by default, and a personal key is simply tried first — so the
 * copy sells it as "faster, no shared limits", never as required.
 */
function LlmKeySection() {
  const toast = useToast();
  const { data, loading, error, reload } = useApi(() => api.llmKey(), []);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const stored = data?.key ?? null;
  const providers = data?.providers ?? [];
  const label = (name) => providers.find((p) => p.provider === name)?.label ?? name;

  async function remove() {
    if (!window.confirm("Remove your AI key? Pulse will go back to its shared AI.")) return;
    setBusy(true);
    try {
      await api.deleteLlmKey();
      toast.success("AI key removed");
      reload();
    } catch (err) {
      toast.error(`Could not remove the AI key: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="llm-heading">
      <div className="mb-4">
        <h2 id="llm-heading" className="text-base font-semibold text-ink-900">
          Your AI key
        </h2>
        <p className="mt-0.5 text-sm text-ink-500">
          Optional. Pulse writes with its shared AI by default; add your own key
          and it is used first — no shared limits, your choice of model.
        </p>
      </div>

      <ErrorBanner message={error} onRetry={reload} />

      {loading && !data ? (
        <Skeleton rows={1} />
      ) : stored && !editing ? (
        <div className="panel flex flex-wrap items-start justify-between gap-4 p-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <h3 className="text-sm font-semibold text-ink-900">{label(stored.provider)}</h3>
              <span className="badge bg-good-wash text-good">in use</span>
            </div>
            <p className="mt-1 font-mono text-[11px] text-ink-500">
              {stored.key_hint ? `key …${stored.key_hint}` : "key saved"}
              {" · "}
              {stored.model ||
                `${providers.find((p) => p.provider === stored.provider)?.default_model ?? "default"} (default)`}
              {stored.last_verified_at && ` · verified ${formatWhen(stored.last_verified_at)}`}
            </p>
            {stored.last_error && (
              <p className="mt-2 break-words rounded bg-bad-wash px-2 py-1 font-mono text-[11px] text-bad">
                {stored.last_error}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button className="btn-quiet text-bad" onClick={remove} disabled={busy}>
              Remove
            </button>
            <button className="btn-ghost" onClick={() => setEditing(true)} disabled={busy}>
              Change key
            </button>
          </div>
        </div>
      ) : (
        <LlmKeyForm
          providers={providers}
          initialProvider={stored?.provider}
          onCancel={stored ? () => setEditing(false) : null}
          onSaved={() => {
            setEditing(false);
            reload();
          }}
        />
      )}
    </section>
  );
}

function LlmKeyForm({ providers, initialProvider, onCancel, onSaved }) {
  const toast = useToast();
  const [provider, setProvider] = useState(
    initialProvider || providers[0]?.provider || "gemini",
  );
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const preset = providers.find((p) => p.provider === provider);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.saveLlmKey({ provider, api_key: apiKey.trim(), model: model.trim() });
      toast.success(`${preset?.label ?? "AI"} key saved — Pulse will use it from now on`);
      setApiKey("");
      onSaved();
    } catch (err) {
      toast.error(`Could not save the AI key: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel space-y-4 p-5" onSubmit={submit} aria-label="AI key">
      <div className="grid gap-4 sm:grid-cols-[minmax(0,12rem)_1fr]">
        <div>
          <label className="label" htmlFor="llm-provider">
            Provider
          </label>
          <select
            id="llm-provider"
            className="input"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            {providers.map((p) => (
              <option key={p.provider} value={p.provider}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <CredentialInput
          field={{
            key: "llm-api-key",
            label: "Your key",
            secret: true,
            required: true,
            help_text: "",
          }}
          value={apiKey}
          onChange={setApiKey}
          placeholder={preset?.key_prefix ? `${preset.key_prefix}…` : ""}
        />
      </div>

      {preset?.key_url && (
        <p className="text-xs text-ink-500">
          Don&apos;t have one?{" "}
          <a
            className="font-medium text-brand-600 hover:underline"
            href={preset.key_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Get a {preset.label} key ↗
          </a>{" "}
          — copy it and paste it above.
        </p>
      )}

      <details className="rounded-lg border border-line px-4 py-2">
        <summary className="cursor-pointer text-xs font-medium text-ink-700">
          Model (optional) — defaults to {preset?.default_model || "the provider's default"}
        </summary>
        <div className="mt-3 pb-2">
          <label className="label" htmlFor="llm-model">
            Model name
          </label>
          <input
            id="llm-model"
            className="input font-mono text-xs"
            placeholder={preset?.default_model ?? ""}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      </details>

      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-ink-400">
          Checked with a tiny request before saving, then encrypted.
        </p>
        <div className="flex shrink-0 gap-2">
          {onCancel && (
            <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
              Cancel
            </button>
          )}
          <button
            type="submit"
            className="btn-primary"
            disabled={busy || apiKey.trim().length < 8}
          >
            {busy ? "Checking…" : "Save key"}
          </button>
        </div>
      </div>
    </form>
  );
}

function HealthRow({ label, value, ok, hint }) {
  return (
    <div className="flex items-start justify-between gap-4 px-5 py-3">
      <div className="min-w-0">
        <dt className="text-sm text-ink-900">{label}</dt>
        {hint && <dd className="mt-0.5 text-xs text-ink-400">{hint}</dd>}
      </div>
      <dd
        className={`shrink-0 font-mono text-xs ${ok ? "text-good" : "text-warn"}`}
      >
        <span className="sr-only">{ok ? "OK:" : "Warning:"} </span>
        {value}
      </dd>
    </div>
  );
}

function PlatformRow({ platform, onConnect, onChanged }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const connection = platform.connection;

  async function verify() {
    setBusy(true);
    try {
      const result = await api.verifyConnection(platform.platform);
      if (result.status === "connected") toast.success(`${platform.display_name} is fine`);
      else
        toast.error(
          result.last_error ||
            `${platform.display_name} credentials were rejected — double-check the key and try again`,
        );
      onChanged();
    } catch (err) {
      toast.error(`Could not verify ${platform.display_name}: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!window.confirm(`Disconnect ${platform.display_name}?`)) return;
    setBusy(true);
    try {
      await api.deleteConnection(platform.platform);
      toast.success("Disconnected");
      onChanged();
    } catch (err) {
      toast.error(`Could not disconnect ${platform.display_name}: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel flex flex-wrap items-start justify-between gap-4 p-5">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <h3 className="text-sm font-semibold text-ink-900">{platform.display_name}</h3>
          {!platform.implemented && (
            <span className="badge bg-canvas text-ink-400">not built</span>
          )}
          {connection?.status === "connected" && (
            <span className="badge bg-good-wash text-good">connected</span>
          )}
          {connection?.status === "invalid" && (
            <span className="badge bg-bad-wash text-bad">reconnect</span>
          )}
        </div>

        {connection?.display_name && (
          <p className="mt-1 font-mono text-[11px] text-ink-500">
            {connection.display_name}
            {connection.last_verified_at &&
              ` · verified ${formatWhen(connection.last_verified_at)}`}
          </p>
        )}
        {connection?.last_error && (
          <p className="mt-2 break-words rounded bg-bad-wash px-2 py-1 font-mono text-[11px] text-bad">
            {connection.last_error}
          </p>
        )}
        {platform.caveat && (
          <p className="mt-2 max-w-lg text-xs leading-relaxed text-ink-400">
            {platform.caveat}
          </p>
        )}
        {!platform.supports_metrics && platform.implemented && (
          <p className="mt-1 text-xs text-ink-400">
            No stats API — views for this platform will stay empty.
          </p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {connection && (
          <>
            <button className="btn-quiet" onClick={verify} disabled={busy}>
              Verify
            </button>
            <button className="btn-quiet text-bad" onClick={disconnect} disabled={busy}>
              Disconnect
            </button>
          </>
        )}
        <button
          className="btn-ghost"
          onClick={onConnect}
          disabled={!platform.implemented}
          title={platform.implemented ? undefined : "This adapter is not finished yet"}
        >
          {connection ? "Replace key" : "Connect"}
        </button>
      </div>
    </div>
  );
}

/* ---- Webhooks ---- */

/**
 * A dialog's options that did not load. Without it the list was simply empty:
 * no events or scopes to tick, a submit button that stayed disabled (or a
 * server 422 asking for one), and nothing saying why.
 */
function ChoicesFailed({ what, onRetry }) {
  return (
    <p role="alert" className="text-xs text-bad">
      Could not load {what}.{" "}
      <button type="button" className="underline" onClick={onRetry}>
        Retry
      </button>
    </p>
  );
}

/**
 * A webhook's recent deliveries, opened on demand, with Redeliver on the ones
 * that failed. The API has listed and re-sent deliveries all along; the page
 * showed only the last error, so an event an endpoint missed while it was down
 * could not be recovered from here once its retries were spent.
 */
function WebhookDeliveries({ webhook, onChanged }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(null);
  const { data, error, loading, reload } = useApi(
    () => (open ? api.webhookDeliveries(webhook.id, { limit: 10 }) : Promise.resolve(null)),
    [webhook.id, open],
  );

  async function redeliver(delivery) {
    setBusy(delivery.id);
    try {
      const result = await api.redeliverWebhook(webhook.id, delivery.id);
      if (result.status === "delivered") toast.success("Redelivered");
      else toast.error(`Redelivery failed${result.error ? `: ${result.error}` : ""}`);
      reload();
      onChanged?.();
    } catch (err) {
      toast.error(`Could not redeliver: ${err.message}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-2">
      <button
        type="button"
        className="btn-quiet -ml-2.5 text-xs"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Hide deliveries" : "Recent deliveries"}
      </button>
      {open &&
        (loading && !data ? (
          <Skeleton rows={2} />
        ) : error ? (
          <ErrorBanner message={`Could not load deliveries: ${error}`} onRetry={reload} />
        ) : !data?.length ? (
          <p className="text-xs text-ink-400">Nothing sent yet.</p>
        ) : (
          <ul className="mt-1 space-y-1.5" aria-label={`Deliveries to ${webhook.url}`}>
            {data.map((delivery) => (
              <li key={delivery.id} className="flex items-start justify-between gap-2 text-xs">
                <span className="min-w-0">
                  <span className="font-medium text-ink-800">{titleize(delivery.event)}</span>{" "}
                  <span className="text-ink-400">
                    {formatWhen(delivery.created_at)} · {delivery.status}
                    {delivery.response_status ? ` · ${delivery.response_status}` : ""}
                  </span>
                  {delivery.error && (
                    <span className="block break-words font-mono text-[11px] text-bad">
                      {delivery.error}
                    </span>
                  )}
                </span>
                {delivery.status === "failed" && (
                  <button
                    type="button"
                    className="btn-quiet shrink-0 text-xs"
                    onClick={() => redeliver(delivery)}
                    disabled={busy !== null}
                  >
                    {busy === delivery.id ? "Sending…" : "Redeliver"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}

function WebhooksSection() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.listWebhooks(), []);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [secret, setSecret] = useState(null);

  async function remove(webhook) {
    if (!window.confirm(`Delete webhook to ${webhook.url}?`)) return;
    try {
      await api.deleteWebhook(webhook.id);
      toast.success("Webhook deleted");
      reload();
    } catch (err) {
      toast.error(`Could not delete webhook: ${err.message}`);
    }
  }

  async function toggle(webhook) {
    try {
      await api.updateWebhook(webhook.id, { is_active: !webhook.is_active });
      toast.success(webhook.is_active ? "Paused" : "Resumed");
      reload();
    } catch (err) {
      toast.error(`Could not ${webhook.is_active ? "pause" : "resume"} webhook: ${err.message}`);
    }
  }

  async function ping(webhook) {
    try {
      const delivery = await api.pingWebhook(webhook.id);
      if (delivery.status === "delivered") toast.success("Ping delivered");
      else
        toast.error(
          delivery.error ||
            "Ping was not delivered — check the endpoint URL is reachable",
        );
    } catch (err) {
      toast.error(`Could not send ping: ${err.message}`);
    }
  }

  return (
    <section>
      <SectionHeader
        title="Outbound webhooks"
        subtitle="HTTP callbacks fired when something happens."
        action={
          <button className="btn-ghost text-sm" onClick={() => setCreating(true)}>
            Add webhook
          </button>
        }
      />
      {loading && !data ? (
        <Skeleton rows={2} />
      ) : error && !data ? (
        // Not the empty state: "No webhooks" over a failed load invited adding
        // a second endpoint next to the one that was already there.
        <ErrorBanner message={`Could not load webhooks: ${error}`} onRetry={reload} />
      ) : (data ?? []).length === 0 ? (
        <Empty
          title="No webhooks"
          hint="Get notified when content is published or fails."
          action={
            <button className="btn-ghost mt-1" onClick={() => setCreating(true)}>
              Add webhook
            </button>
          }
        />
      ) : (
        <div className="space-y-3">
          {data.map((webhook) => (
            <div key={webhook.id} className="panel p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="truncate font-mono text-xs text-ink-900">
                      {webhook.url}
                    </p>
                    {!webhook.is_active && (
                      <span className="badge bg-canvas text-ink-400">paused</span>
                    )}
                    {webhook.consecutive_failures > 0 && (
                      <span className="badge bg-bad-wash text-bad">
                        {webhook.consecutive_failures} failures
                      </span>
                    )}
                  </div>
                  {webhook.description && (
                    <p className="mt-1 text-xs text-ink-500">{webhook.description}</p>
                  )}
                  <p className="mt-1 flex flex-wrap gap-1.5">
                    {webhook.events.map((event) => (
                      <span key={event} className="chip">{titleize(event)}</span>
                    ))}
                  </p>
                  {webhook.last_error && (
                    <p className="mt-2 break-words rounded bg-bad-wash px-2 py-1 font-mono text-[11px] text-bad">
                      {webhook.last_error}
                    </p>
                  )}
                  <WebhookDeliveries webhook={webhook} onChanged={reload} />
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button className="btn-quiet" onClick={() => setEditing(webhook)}>
                    Edit
                  </button>
                  <button className="btn-quiet" onClick={() => ping(webhook)}>
                    Ping
                  </button>
                  <button className="btn-quiet" onClick={() => toggle(webhook)}>
                    {webhook.is_active ? "Pause" : "Resume"}
                  </button>
                  <button className="btn-quiet text-bad" onClick={() => remove(webhook)}>
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {creating && (
        <CreateWebhookDialog
          onClose={() => setCreating(false)}
          onDone={(created) => {
            setCreating(false);
            setSecret(created.secret);
            reload();
          }}
        />
      )}

      {editing && (
        <EditWebhookDialog
          webhook={editing}
          onClose={() => setEditing(null)}
          onDone={() => {
            setEditing(null);
            reload();
          }}
        />
      )}

      {secret && (
        <OneTimeSecret title="Signing secret" value={secret} onClose={() => setSecret(null)} />
      )}
    </section>
  );
}

function CreateWebhookDialog({ onClose, onDone }) {
  const toast = useToast();
  const { data: events, error: eventsError, reload: reloadEvents } = useApi(
    () => api.webhookEvents(),
    [],
  );
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);

  function toggleEvent(event) {
    setSelected((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event],
    );
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api.createWebhook({
        url,
        events: selected,
        description,
      });
      onDone(result);
    } catch (err) {
      toast.error(`Could not create webhook: ${err.message}`);
      setBusy(false);
    }
  }

  return (
    <Dialog
      label="Add webhook"
      onClose={onClose}
      closable={!busy}
      onSubmit={submit}
    >
      <h2 className="font-display text-2xl text-ink-900">Add webhook</h2>

      <div>
        <label className="label" htmlFor="wh-url">Endpoint URL</label>
        <input
          id="wh-url"
          className="input font-mono text-xs"
          type="url"
          required
          placeholder="https://example.com/webhook"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </div>

      <div>
        <label className="label" htmlFor="wh-desc">
          Description <span className="normal-case tracking-normal">(optional)</span>
        </label>
        <input
          id="wh-desc"
          className="input"
          maxLength={200}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      <fieldset>
        <legend className="label mb-2">Events</legend>
        <div className="space-y-2">
          {eventsError && !events && (
            <ChoicesFailed what="the event list" onRetry={reloadEvents} />
          )}
          {(events ?? []).map((ev) => (
            <label key={ev.event} className="flex items-start gap-2.5 text-sm text-ink-700">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={selected.includes(ev.event)}
                onChange={() => toggleEvent(ev.event)}
              />
              <span>
                <span className="font-medium">{titleize(ev.event)}</span>
                <span className="mt-0.5 block text-xs text-ink-400">{ev.description}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex justify-end gap-2 pt-2">
        <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn-primary"
          disabled={busy || !url || selected.length === 0}
        >
          {busy ? "Creating…" : "Create"}
        </button>
      </div>
    </Dialog>
  );
}

function EditWebhookDialog({ webhook, onClose, onDone }) {
  const toast = useToast();
  const { data: events, error: eventsError, reload: reloadEvents } = useApi(
    () => api.webhookEvents(),
    [],
  );
  const [url, setUrl] = useState(webhook.url);
  const [description, setDescription] = useState(webhook.description || "");
  const [selected, setSelected] = useState(webhook.events);
  const [busy, setBusy] = useState(false);

  function toggleEvent(event) {
    setSelected((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event],
    );
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.updateWebhook(webhook.id, { url, events: selected, description });
      toast.success("Webhook updated");
      onDone();
    } catch (err) {
      toast.error(`Could not update webhook: ${err.message}`);
      setBusy(false);
    }
  }

  return (
    <Dialog label="Edit webhook" onClose={onClose} closable={!busy} onSubmit={submit}>
      <h2 className="font-display text-2xl text-ink-900">Edit webhook</h2>

      <div>
        <label className="label" htmlFor="wh-edit-url">Endpoint URL</label>
        <input
          id="wh-edit-url"
          className="input font-mono text-xs"
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </div>

      <div>
        <label className="label" htmlFor="wh-edit-desc">
          Description <span className="normal-case tracking-normal">(optional)</span>
        </label>
        <input
          id="wh-edit-desc"
          className="input"
          maxLength={200}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      <fieldset>
        <legend className="label mb-2">Events</legend>
        <div className="space-y-2">
          {eventsError && !events && (
            <ChoicesFailed what="the event list" onRetry={reloadEvents} />
          )}
          {(events ?? []).map((ev) => (
            <label key={ev.event} className="flex items-start gap-2.5 text-sm text-ink-700">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={selected.includes(ev.event)}
                onChange={() => toggleEvent(ev.event)}
              />
              <span>
                <span className="font-medium">{titleize(ev.event)}</span>
                <span className="mt-0.5 block text-xs text-ink-400">{ev.description}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex justify-end gap-2 pt-2">
        <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn-primary"
          disabled={busy || !url || selected.length === 0}
        >
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </Dialog>
  );
}

/* ---- API Keys ---- */

function ApiKeysSection() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.listApiKeys(), []);
  const [creating, setCreating] = useState(false);
  const [token, setToken] = useState(null);

  async function revoke(key) {
    if (!window.confirm(`Revoke API key "${key.name}"?`)) return;
    try {
      await api.revokeApiKey(key.id);
      toast.success("Key revoked");
      reload();
    } catch (err) {
      toast.error(`Could not revoke API key "${key.name}": ${err.message}`);
    }
  }

  return (
    <section>
      <SectionHeader
        title="API keys"
        subtitle="Machine credentials scoped to a project."
        action={
          <button className="btn-ghost text-sm" onClick={() => setCreating(true)}>
            Create key
          </button>
        }
      />
      {loading && !data ? (
        <Skeleton rows={2} />
      ) : error && !data ? (
        // As with webhooks: an empty state here read as "you have no keys" and
        // sent people to mint another one.
        <ErrorBanner message={`Could not load API keys: ${error}`} onRetry={reload} />
      ) : (data ?? []).length === 0 ? (
        <Empty
          title="No API keys"
          hint="Create a key to let scripts file ideas or read analytics."
          action={
            <button className="btn-ghost mt-1" onClick={() => setCreating(true)}>
              Create key
            </button>
          }
        />
      ) : (
        <div className="space-y-3">
          {data.map((key) => (
            <div key={key.id} className="panel flex items-start justify-between gap-4 p-5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-ink-900">{key.name}</p>
                  <span className="font-mono text-[11px] text-ink-400">{key.prefix}…</span>
                  {key.revoked_at && (
                    <span className="badge bg-canvas text-ink-400">revoked</span>
                  )}
                </div>
                <p className="mt-1 flex flex-wrap gap-1.5">
                  {key.scopes.map((scope) => (
                    <span key={scope} className="chip">{titleize(scope)}</span>
                  ))}
                </p>
                <p className="mt-1 text-[11px] text-ink-400">
                  Created {formatWhen(key.created_at)}
                  {key.last_used_at && <> · last used {formatWhen(key.last_used_at)}</>}
                  {key.expires_at && <> · expires {formatWhen(key.expires_at)}</>}
                </p>
              </div>
              {!key.revoked_at && (
                <button className="btn-quiet shrink-0 text-bad" onClick={() => revoke(key)}>
                  Revoke
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {creating && (
        <CreateApiKeyDialog
          onClose={() => setCreating(false)}
          onDone={(created) => {
            setCreating(false);
            setToken(created.token);
            reload();
          }}
        />
      )}

      {token && <OneTimeSecret title="API token" value={token} onClose={() => setToken(null)} />}
    </section>
  );
}

function CreateApiKeyDialog({ onClose, onDone }) {
  const toast = useToast();
  const {
    data: projects,
    error: projectsError,
    reload: reloadProjects,
  } = useApi(() => api.listProjects(), []);
  const { data: scopes, error: scopesError, reload: reloadScopes } = useApi(
    () => api.apiKeyScopes(),
    [],
  );
  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("");
  const [selected, setSelected] = useState([]);
  const [expiryDays, setExpiryDays] = useState("");
  const [busy, setBusy] = useState(false);

  function toggleScope(scope) {
    setSelected((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api.createApiKey({
        project_id: Number(projectId),
        name,
        scopes: selected,
        expires_in_days: expiryDays ? Number(expiryDays) : null,
      });
      onDone(result);
    } catch (err) {
      toast.error(`Could not create API key: ${err.message}`);
      setBusy(false);
    }
  }

  return (
    <Dialog
      label="Create API key"
      onClose={onClose}
      closable={!busy}
      onSubmit={submit}
    >
      <h2 className="font-display text-2xl text-ink-900">Create API key</h2>

      <div>
        <label className="label" htmlFor="ak-project">Project</label>
        <select
          id="ak-project"
          className="input"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          required
        >
          <option value="">Select a project</option>
          {(projects ?? []).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        {projectsError && !projects && (
          <ChoicesFailed what="your projects" onRetry={reloadProjects} />
        )}
      </div>

      <div>
        <label className="label" htmlFor="ak-name">Key name</label>
        <input
          id="ak-name"
          className="input"
          required
          maxLength={120}
          placeholder="CI deploy key"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>

      <fieldset>
        <legend className="label mb-2">Scopes</legend>
        <div className="space-y-2">
          {scopesError && !scopes && (
            <ChoicesFailed what="the scope list" onRetry={reloadScopes} />
          )}
          {(scopes ?? []).map((s) => (
            <label key={s.scope} className="flex items-start gap-2.5 text-sm text-ink-700">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={selected.includes(s.scope)}
                onChange={() => toggleScope(s.scope)}
              />
              <span>
                <span className="font-medium">{titleize(s.scope)}</span>
                <span className="mt-0.5 block text-xs text-ink-400">{s.description}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <label className="label" htmlFor="ak-expiry">
          Expires in days <span className="normal-case tracking-normal">(blank = never)</span>
        </label>
        <input
          id="ak-expiry"
          className="input"
          type="number"
          min={1}
          max={365}
          value={expiryDays}
          onChange={(e) => setExpiryDays(e.target.value)}
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn-primary"
          disabled={busy || !projectId || !name || selected.length === 0}
        >
          {busy ? "Creating…" : "Create"}
        </button>
      </div>
    </Dialog>
  );
}

function ConnectDialog({ platform, onClose, onDone }) {
  const toast = useToast();
  const guide = guideFor(platform);
  const [values, setValues] = useState(() =>
    Object.fromEntries(platform.credential_fields.map((field) => [field.key, ""])),
  );
  const [busy, setBusy] = useState(false);
  const replacing = Boolean(platform.connection);

  // Optional settings with sensible defaults (branch, PDS URL, visibility…)
  // are what make a two-field form look like a six-field one. They go behind
  // a disclosure. An optional *secret* stays in view: leaving a token blank
  // changes which credential is used, which is not a default to hide.
  const primary = platform.credential_fields.filter((f) => f.required || f.secret);
  const extra = platform.credential_fields.filter((f) => !f.required && !f.secret);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    // Optional blanks are omitted rather than sent as "" — the API validates
    // supplied keys against the adapter's field list.
    const payload = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value.trim()),
    );
    try {
      await api.saveConnection(platform.platform, payload);
      toast.success(`${platform.display_name} connected`);
      onDone();
    } catch (err) {
      toast.error(`Could not connect ${platform.display_name}: ${err.message}`);
      setBusy(false);
    }
  }

  function field(f, index) {
    return (
      <CredentialInput
        key={f.key}
        field={f}
        autoFocus={index === 0}
        value={values[f.key]}
        onChange={(value) => setValues((current) => ({ ...current, [f.key]: value }))}
      />
    );
  }

  return (
    <Dialog
      label={`Connect ${platform.display_name}`}
      onClose={onClose}
      closable={!busy}
      width="md"
      onSubmit={submit}
    >
      <h2 className="font-display text-2xl text-ink-900">
        {replacing ? "Update" : "Connect"} {platform.display_name}
      </h2>
      {platform.caveat && (
        <p className="rounded-lg bg-warn-wash px-3 py-2 text-xs leading-relaxed text-warn">
          {platform.caveat}
        </p>
      )}

      {guide.steps.length > 0 && (
        <div className="rounded-lg border border-line bg-canvas px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <p className="label !mb-0">How to get your key</p>
            {guide.setupUrl && (
              <a
                className="text-xs font-medium text-brand-600 hover:underline"
                href={guide.setupUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open {platform.display_name} settings ↗
              </a>
            )}
          </div>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs leading-relaxed text-ink-700">
            {guide.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      )}

      {primary.map(field)}

      {extra.length > 0 && (
        <details className="group rounded-lg border border-line px-4 py-2">
          <summary className="cursor-pointer text-xs font-medium text-ink-700">
            Optional settings ({extra.length}) — the defaults work for most people
          </summary>
          <div className="mt-3 space-y-4 pb-2">
            {extra.map((f, i) => field(f, primary.length + i))}
          </div>
        </details>
      )}

      <p className="text-xs text-ink-400">
        Verified against {platform.display_name} before saving.
      </p>

      <div className="flex justify-end gap-2 pt-1">
        <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Verifying…" : replacing ? "Save new key" : "Connect"}
        </button>
      </div>
    </Dialog>
  );
}

/** One credential field, with a reveal toggle on secrets so a paste can be checked. */
function CredentialInput({ field, value, onChange, autoFocus, placeholder }) {
  const [revealed, setRevealed] = useState(false);
  const id = `cred-${field.key}`;
  return (
    <div>
      <label className="label" htmlFor={id}>
        {field.label}
        {!field.required && (
          <span className="normal-case tracking-normal"> (optional)</span>
        )}
      </label>
      <div className="relative">
        <input
          id={id}
          className={`input font-mono text-xs ${field.secret ? "pr-16" : ""}`}
          type={field.secret && !revealed ? "password" : "text"}
          required={field.required}
          autoComplete="off"
          spellCheck={false}
          data-autofocus={autoFocus || undefined}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        {field.secret && (
          <button
            type="button"
            className="absolute inset-y-0 right-2 my-auto h-6 rounded px-2 text-[11px] text-ink-500 hover:text-ink-900"
            onClick={() => setRevealed((r) => !r)}
            aria-controls={id}
            aria-pressed={revealed}
          >
            {revealed ? "Hide" : "Show"}
          </button>
        )}
      </div>
      {field.help_text && (
        <p className="mt-1 text-xs text-ink-400">{field.help_text}</p>
      )}
    </div>
  );
}

/**
 * A secret the server shows exactly once.
 *
 * It had no copy button and no label, and the dialog closed on Escape or a
 * stray click on the backdrop — after which the secret was gone and the only
 * way back was to rotate it. Until it has been copied, only the explicit
 * button closes the dialog (still a keyboard-reachable control, so nothing is
 * trapped).
 */
export function OneTimeSecret({ title, value, onClose }) {
  const [copied, setCopied] = useState(null);
  const fieldId = `secret-${title.toLowerCase().replace(/\W+/g, "-")}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied("ok");
    } catch {
      setCopied("failed");
      document.getElementById(fieldId)?.select();
    }
  }

  return (
    <Dialog label={title} onClose={onClose} closable={copied === "ok"}>
      <h2 id={`${fieldId}-title`} className="font-display text-2xl text-ink-900">
        {title}
      </h2>
      <p className="text-sm text-ink-700">Copy this now — it will not be shown again.</p>
      <div className="flex gap-2">
        <input
          id={fieldId}
          aria-labelledby={`${fieldId}-title`}
          readOnly
          className="input flex-1 font-mono text-xs"
          value={value}
          onFocus={(e) => e.target.select()}
        />
        <button type="button" className="btn-ghost" onClick={copy}>
          {copied === "ok" ? "Copied" : "Copy"}
        </button>
      </div>
      <p role="status" aria-live="polite" className="min-h-[1rem] text-xs text-ink-500">
        {copied === "ok" && "Copied to the clipboard."}
        {copied === "failed" &&
          "Your browser blocked clipboard access — the value is selected, press Ctrl+C (⌘C) to copy it."}
      </p>
      <div className="flex justify-end pt-1">
        <button type="button" className="btn-primary" onClick={onClose}>
          {copied === "ok" ? "Done" : "I've saved it"}
        </button>
      </div>
    </Dialog>
  );
}

/* ---- Export ---- */

/**
 * Download everything the account has written.
 *
 * Above Delete account on purpose: erasing was possible and taking the work
 * out first was not. The file is the API's JSON as-is, saved under a dated
 * name; credentials are never in it (``app.services.account_export``).
 */
export function ExportAccountSection() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    try {
      const data = await api.exportAccount();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `pulse-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${data.content.length} pieces from ${data.projects.length} projects`);
    } catch (err) {
      toast.error(`Could not export: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="export-heading" className="border-t border-line pt-8">
      <h2 id="export-heading" className="text-base font-semibold text-ink-900">
        Download your work
      </h2>
      <p className="mt-0.5 max-w-2xl text-sm text-ink-500">
        Every piece with its full text and where it went live, your projects, templates and
        ideas, as one JSON file. No passwords or connection keys are included.
      </p>
      <button type="button" className="btn-ghost mt-3" onClick={download} disabled={busy}>
        {busy ? "Preparing…" : "Download my data"}
      </button>
    </section>
  );
}

/* ---- Delete account ---- */

/**
 * Erase the account and everything in it.
 *
 * Asks for the password, as the API does, and says plainly what goes and
 * what cannot be reached from here — posts already on other platforms stay
 * there. On success the session is dropped and the person lands on the front
 * page, because there is no account left to show them.
 */
function DeleteAccountSection() {
  const [open, setOpen] = useState(false);
  return (
    <section aria-labelledby="delete-account-heading" className="border-t border-line pt-8">
      <h2 id="delete-account-heading" className="text-base font-semibold text-ink-900">
        Delete account
      </h2>
      <p className="mt-0.5 max-w-2xl text-sm text-ink-500">
        Erases your projects, content, connected accounts and their keys, API keys,
        webhooks, triggers, templates and the newsletter sign-ups collected on your pages.
        Posts already published to other platforms stay there.
      </p>
      <button type="button" className="btn-ghost mt-3 text-bad" onClick={() => setOpen(true)}>
        Delete my account…
      </button>
      {open && <DeleteAccountDialog onClose={() => setOpen(false)} />}
    </section>
  );
}

function DeleteAccountDialog({ onClose }) {
  const { logout } = useAuth();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    if (!password) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(password);
      logout();
      window.location.assign("/");
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Dialog label="Delete account" onClose={onClose} closable={!busy} onSubmit={submit} width="md">
      <h2 className="font-display text-2xl text-ink-900">Delete your account?</h2>
      <p className="text-sm text-ink-600">
        This cannot be undone. Enter your password to confirm.
      </p>
      <div>
        <label className="label" htmlFor="delete-account-password">Password</label>
        <input
          id="delete-account-password"
          className="input"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "delete-account-error" : undefined}
        />
      </div>
      {error && (
        <p id="delete-account-error" className="text-sm text-bad" role="alert">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2 pt-2">
        <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="btn-primary bg-bad hover:bg-bad/90" disabled={busy || !password}>
          {busy ? "Deleting…" : "Delete everything"}
        </button>
      </div>
    </Dialog>
  );
}

