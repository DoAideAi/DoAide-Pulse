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

      <div className="border-t border-line pt-6">
        <h2 className="text-base font-semibold text-ink-900">Advanced</h2>
        <p className="mt-0.5 text-sm text-ink-500">
          Webhooks, API keys and server status — for developers and operators.
          You don't need any of this to publish.
        </p>
      </div>

      <WebhooksSection />
      <ApiKeysSection />

      <section>
        <SectionHeader
          title="Service health"
          subtitle="What is configured on the server."
        />
        {health.loading && !health.data ? (
          <Skeleton rows={1} />
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

function WebhooksSection() {
  const toast = useToast();
  const { data, loading, reload } = useApi(() => api.listWebhooks(), []);
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
      ) : (data ?? []).length === 0 ? (
        <Empty
          title="No webhooks"
          hint="Get notified when content is published or fails."
          action={
            <button className="btn-primary mt-1" onClick={() => setCreating(true)}>
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
        <Dialog label="Signing secret" onClose={() => setSecret(null)}>
          <h2 className="font-display text-2xl text-ink-900">Signing secret</h2>
          <p className="text-sm text-ink-700">
            Copy this now — it will not be shown again.
          </p>
          <input
            readOnly
            className="input font-mono text-xs"
            value={secret}
            onFocus={(e) => e.target.select()}
          />
          <div className="flex justify-end pt-1">
            <button className="btn-primary" onClick={() => setSecret(null)}>
              Done
            </button>
          </div>
        </Dialog>
      )}
    </section>
  );
}

function CreateWebhookDialog({ onClose, onDone }) {
  const toast = useToast();
  const { data: events } = useApi(() => api.webhookEvents(), []);
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
  const { data: events } = useApi(() => api.webhookEvents(), []);
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
  const { data, loading, reload } = useApi(() => api.listApiKeys(), []);
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
      ) : (data ?? []).length === 0 ? (
        <Empty
          title="No API keys"
          hint="Create a key to let scripts file ideas or read analytics."
          action={
            <button className="btn-primary mt-1" onClick={() => setCreating(true)}>
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

      {token && (
        <Dialog label="API token" onClose={() => setToken(null)}>
          <h2 className="font-display text-2xl text-ink-900">API token</h2>
          <p className="text-sm text-ink-700">
            Copy this now — it will not be shown again.
          </p>
          <input
            readOnly
            className="input font-mono text-xs"
            value={token}
            onFocus={(e) => e.target.select()}
          />
          <div className="flex justify-end pt-1">
            <button className="btn-primary" onClick={() => setToken(null)}>
              Done
            </button>
          </div>
        </Dialog>
      )}
    </section>
  );
}

function CreateApiKeyDialog({ onClose, onDone }) {
  const toast = useToast();
  const { data: projects } = useApi(() => api.listProjects(), []);
  const { data: scopes } = useApi(() => api.apiKeyScopes(), []);
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
function CredentialInput({ field, value, onChange, autoFocus }) {
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
