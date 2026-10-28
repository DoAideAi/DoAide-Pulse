/**
 * The Settings page's service-health panel.
 *
 * Every row in it — the provider chain, the open breakers, the GitHub token,
 * credential encryption — is a field only `GET /health/detail` returns. The
 * public `/health` is a liveness probe and deliberately withholds all of them,
 * so a page that asked it instead rendered a fully configured server as "none
 * configured", "anonymous" and "off": three rows telling the operator to go and
 * set environment variables that were already set.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Settings from "./Settings";
import { api } from "../lib/api";
import { ROUTER_FUTURE } from "../lib/routerFuture";

vi.mock("../lib/api", () => ({
  api: {
    platforms: vi.fn(),
    deleteAccount: vi.fn(),
    healthDetail: vi.fn(),
    health: vi.fn(),
    verifyConnection: vi.fn(),
    deleteConnection: vi.fn(),
    saveConnection: vi.fn(),
    listWebhooks: vi.fn(),
    webhookEvents: vi.fn(),
    createWebhook: vi.fn(),
    deleteWebhook: vi.fn(),
    updateWebhook: vi.fn(),
    pingWebhook: vi.fn(),
    exportAccount: vi.fn(),
    webhookDeliveries: vi.fn(),
    redeliverWebhook: vi.fn(),
    listApiKeys: vi.fn(),
    apiKeyScopes: vi.fn(),
    createApiKey: vi.fn(),
    revokeApiKey: vi.fn(),
    listProjects: vi.fn(),
    llmKey: vi.fn(),
    saveLlmKey: vi.fn(),
    deleteLlmKey: vi.fn(),
  },
}));

const toast = { success: vi.fn(), error: vi.fn() };
vi.mock("../components/ui/Toast", () => ({ useToast: () => toast }));

// One object, not a fresh `{refresh: vi.fn()}` per call: the page calls
// `refresh()` to re-read the user after a connection changes, and a mock that
// is rebuilt on every render can never be asserted against.
const auth = { user: { email: "you@example.com" }, refresh: vi.fn(), logout: vi.fn() };
vi.mock("../hooks/useAuth", () => ({ useAuth: () => auth }));

const LLM_PROVIDERS = [
  {
    provider: "gemini",
    label: "Google Gemini",
    default_model: "gemini-flash-latest",
    key_url: "https://aistudio.google.com/app/apikey",
    key_prefix: "AIza",
  },
  {
    provider: "openai",
    label: "OpenAI",
    default_model: "gpt-4o-mini",
    key_url: "https://platform.openai.com/api-keys",
    key_prefix: "sk-",
  },
];

function draw() {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <Settings />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.platforms.mockResolvedValue([]);
  api.healthDetail.mockResolvedValue({
    status: "ok",
    database: { status: "ok", required: true, detail: "" },
    redis: { status: "ok", required: false, detail: "" },
    llm_providers: ["openrouter", "groq"],
    llm_breakers_open: {},
    github_configured: true,
    credential_encryption: true,
    implemented_platforms: ["devto"],
  });
  api.listWebhooks.mockResolvedValue([]);
  api.webhookEvents.mockResolvedValue([]);
  api.listApiKeys.mockResolvedValue([]);
  api.apiKeyScopes.mockResolvedValue([]);
  api.listProjects.mockResolvedValue([]);
  api.llmKey.mockResolvedValue({ providers: LLM_PROVIDERS, key: null });
});

describe("service health", () => {
  it("reads the authenticated detail endpoint, not the public probe", async () => {
    draw();
    await screen.findByText("openrouter → groq");

    expect(api.healthDetail).toHaveBeenCalled();
    expect(api.health).not.toHaveBeenCalled();
  });

  it("reports a configured server as configured", async () => {
    draw();

    expect(await screen.findByText("openrouter → groq")).toBeInTheDocument();
    expect(screen.getByText("token set")).toBeInTheDocument();
    expect(screen.getByText("on")).toBeInTheDocument();
  });

  it("still reports an unconfigured one honestly", async () => {
    api.healthDetail.mockResolvedValue({
      status: "ok",
      llm_providers: [],
      llm_breakers_open: {},
      github_configured: false,
      credential_encryption: false,
    });
    draw();

    expect(await screen.findByText("none configured")).toBeInTheDocument();
    expect(screen.getByText("anonymous")).toBeInTheDocument();
    expect(screen.getByText("off")).toBeInTheDocument();
  });

  it("says it could not check, rather than reporting a broken server, when the read fails", async () => {
    api.healthDetail.mockRejectedValue(new Error("Service Unavailable"));
    draw();

    expect(
      await screen.findByText(/Could not check service health: Service Unavailable/),
    ).toBeInTheDocument();
    expect(screen.queryByText("none configured")).toBeNull();
    expect(screen.queryByText("anonymous")).toBeNull();

    api.healthDetail.mockResolvedValue({
      status: "ok", llm_providers: ["openrouter"], llm_breakers_open: {},
      github_configured: true, credential_encryption: true,
    });
    await userEvent.click(screen.getAllByRole("button", { name: /Retry|Try again/ })[0]);
    expect(await screen.findByText("openrouter")).toBeInTheDocument();
  });

  it("names the providers being skipped while their cool-down runs", async () => {
    api.healthDetail.mockResolvedValue({
      status: "ok",
      llm_providers: ["openrouter", "groq"],
      llm_breakers_open: { groq: { failures: 0, seconds_until_retry: 240 } },
      github_configured: true,
      credential_encryption: true,
    });
    draw();

    expect(await screen.findByText("groq")).toBeInTheDocument();
  });
});

/**
 * The other two thirds of this page: the platform rows and the dialog that
 * connects one.
 *
 * Both are entirely about a credential the API will never hand back. A row
 * cannot show you the key it holds, so what it *can* show — connected or
 * needing a reconnect, which handle it authenticated as, what the platform
 * said when it last refused — is the whole of the operator's read on whether
 * publishing will work tonight. And "Connect" on a platform Pulse has no
 * adapter for, or a Disconnect that goes through without a confirm, are both
 * failures the health panel above says nothing about.
 */

/** A platform capability row as `GET /settings/platforms` returns one. */
function platform(overrides = {}) {
  return {
    platform: "devto",
    display_name: "Dev.to",
    implemented: true,
    supports_metrics: true,
    caveat: "",
    credential_fields: [
      { key: "api_key", label: "API key", help_text: "", secret: true, required: true },
    ],
    connection: null,
    ...overrides,
  };
}

/** The connection sub-object, present only once a key has been saved. */
function connection(overrides = {}) {
  return {
    id: 1,
    platform: "devto",
    status: "connected",
    display_name: "@you",
    last_verified_at: null,
    last_error: null,
    ...overrides,
  };
}

describe("platform rows", () => {
  it("lists an adapter that is not built as coming soon, with nothing to click", async () => {
    api.platforms.mockResolvedValue([
      platform({ platform: "medium", display_name: "Medium", implemented: false }),
    ]);
    draw();

    expect(await screen.findByText("Coming soon")).toBeInTheDocument();
    expect(screen.getByText("Medium")).toHaveAttribute(
      "title",
      "This adapter is not finished yet",
    );
    expect(screen.queryByRole("button", { name: /Connect/ })).not.toBeInTheDocument();
  });

  it("leaves Connect live on one that is", async () => {
    api.platforms.mockResolvedValue([platform()]);
    draw();

    expect(await screen.findByRole("button", { name: "Connect Dev.to" })).toBeEnabled();
    expect(screen.queryByText("Coming soon")).not.toBeInTheDocument();
  });

  it("shows Verify and Disconnect only once a key is stored", async () => {
    api.platforms.mockResolvedValue([platform()]);
    draw();
    await screen.findByRole("button", { name: "Connect Dev.to" });

    expect(screen.queryByRole("button", { name: "Verify" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Disconnect" }),
    ).not.toBeInTheDocument();
  });

  it("calls the second key a replacement, because the first is unreadable", async () => {
    api.platforms.mockResolvedValue([platform({ connection: connection() })]);
    draw();

    expect(await screen.findByRole("button", { name: "Replace key" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Verify" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
  });

  it("badges a connection the platform has stopped accepting as needing a reconnect", async () => {
    api.platforms.mockResolvedValue([
      platform({
        connection: connection({ status: "invalid", last_error: "401 Unauthorized" }),
      }),
    ]);
    draw();

    expect(await screen.findByText("reconnect")).toBeInTheDocument();
    expect(screen.queryByText("connected")).not.toBeInTheDocument();
    expect(screen.getByText("401 Unauthorized")).toBeInTheDocument();
  });

  it("names the handle the stored key authenticated as", async () => {
    api.platforms.mockResolvedValue([platform({ connection: connection() })]);
    draw();

    expect(await screen.findByText(/@you/)).toBeInTheDocument();
  });

  it("says when the key was last known to work, and stays quiet when never", async () => {
    // A stored key is only evidence that something was pasted in; the verified
    // time is the evidence it still opens the door. Saying nothing is right for
    // a key nobody has checked — a blank date would look like a bug.
    api.platforms.mockResolvedValue([
      platform({ connection: connection({ last_verified_at: "2026-08-13T09:00:00Z" }) }),
    ]);
    const { unmount } = draw();

    expect(await screen.findByText(/@you · verified /)).toBeInTheDocument();
    unmount();

    api.platforms.mockResolvedValue([platform({ connection: connection() })]);
    draw();

    // Scoped to the handle line — the panel's own subtitle also says
    // "verified", about when keys are checked rather than about this one.
    expect(await screen.findByText("@you")).toHaveTextContent(/^@you$/);
  });

  it("says so when a platform will never report views", async () => {
    api.platforms.mockResolvedValue([platform({ supports_metrics: false })]);
    draw();

    expect(await screen.findByText(/No stats API/)).toBeInTheDocument();
  });

  it("does not promise stats about an adapter that does not exist", async () => {
    api.platforms.mockResolvedValue([
      platform({ supports_metrics: false, implemented: false }),
    ]);
    draw();

    await screen.findByText("Coming soon");
    expect(screen.queryByText(/No stats API/)).not.toBeInTheDocument();
  });

  it("surfaces the adapter's caveat", async () => {
    api.platforms.mockResolvedValue([
      platform({
        caveat: "Medium's API is write-only and deprecated.",
        connection: connection(),
      }),
    ]);
    draw();

    expect(
      await screen.findByText("Medium's API is write-only and deprecated."),
    ).toBeInTheDocument();
  });
});

describe("verifying a stored key", () => {
  beforeEach(() => {
    api.platforms.mockResolvedValue([platform({ connection: connection() })]);
  });

  it("reports a key the platform still accepts", async () => {
    api.verifyConnection.mockResolvedValue({ status: "connected" });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Verify" }));

    expect(api.verifyConnection).toHaveBeenCalledWith("devto");
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Dev.to is fine"));
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("re-reads the row afterwards, so a status that changed is the one shown", async () => {
    api.verifyConnection.mockResolvedValue({ status: "connected" });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Verify" }));

    // Once on mount, once because verifying may have changed what it says.
    await waitFor(() => expect(api.platforms).toHaveBeenCalledTimes(2));
    expect(auth.refresh).toHaveBeenCalled();
  });

  it("shows what the platform said when it refuses", async () => {
    api.verifyConnection.mockResolvedValue({
      status: "invalid",
      last_error: "403 Forbidden",
    });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Verify" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("403 Forbidden"));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("still says something when it refuses without a reason", async () => {
    api.verifyConnection.mockResolvedValue({ status: "invalid", last_error: null });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Verify" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Dev.to credentials were rejected — double-check the key and try again"),
    );
  });

  it("does not reload on a request that never reached the server", async () => {
    api.verifyConnection.mockRejectedValue(new Error("Gateway Timeout"));
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Verify" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not verify Dev.to: Gateway Timeout"));
    expect(api.platforms).toHaveBeenCalledTimes(1);
  });

  it("frees the buttons again after a failure, so the row is not stuck", async () => {
    api.verifyConnection.mockRejectedValue(new Error("nope"));
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Verify" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Verify" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeEnabled();
  });
});

describe("disconnecting", () => {
  beforeEach(() => {
    api.platforms.mockResolvedValue([platform({ connection: connection() })]);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("asks before throwing a credential away", async () => {
    const confirm = vi.fn().mockReturnValue(false);
    vi.stubGlobal("confirm", confirm);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Disconnect" }));

    expect(confirm).toHaveBeenCalledWith("Disconnect Dev.to?");
    expect(api.deleteConnection).not.toHaveBeenCalled();
  });

  it("deletes the connection once that is answered", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    api.deleteConnection.mockResolvedValue(null);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Disconnect" }));

    expect(api.deleteConnection).toHaveBeenCalledWith("devto");
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Disconnected"));
    await waitFor(() => expect(api.platforms).toHaveBeenCalledTimes(2));
  });

  it("keeps the row when the delete fails", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    api.deleteConnection.mockRejectedValue(new Error("Conflict"));
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Disconnect" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not disconnect Dev.to: Conflict"));
    expect(api.platforms).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeEnabled();
  });
});

describe("the connect dialog", () => {
  /**
   * The dialog's own submit.
   *
   * Scoped to the dialog on purpose: the row that opened it is still mounted
   * behind the backdrop with a "Connect" button of its own, so an unscoped
   * query matches two buttons and the test reads as a component bug.
   */
  function submitButton() {
    return within(screen.getByRole("dialog")).getByRole("button", { name: "Connect" });
  }

  const twoFields = [
    { key: "api_key", label: "API key", help_text: "Find it under Settings → Account", secret: true, required: true },
    { key: "org_id", label: "Organisation", help_text: "", secret: false, required: false },
  ];

  it("renders one input per credential field the adapter declares", async () => {
    api.platforms.mockResolvedValue([platform({ credential_fields: twoFields })]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText(/API key/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/Organisation/)).toBeInTheDocument();
    expect(
      within(dialog).getByText("Find it under Settings → Account"),
    ).toBeInTheDocument();
  });

  it("masks a secret field and leaves a non-secret one readable", async () => {
    api.platforms.mockResolvedValue([platform({ credential_fields: twoFields })]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));

    expect(screen.getByLabelText(/API key/)).toHaveAttribute("type", "password");
    expect(screen.getByLabelText(/Organisation/)).toHaveAttribute("type", "text");
  });

  it("marks the optional field optional and requires the rest", async () => {
    api.platforms.mockResolvedValue([platform({ credential_fields: twoFields })]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));

    expect(screen.getByLabelText(/Organisation \(optional\)/)).not.toBeRequired();
    expect(screen.getByLabelText(/API key/)).toBeRequired();
  });

  it("sends what was typed and saves nothing for the blank optional field", async () => {
    api.platforms.mockResolvedValue([platform({ credential_fields: twoFields })]);
    api.saveConnection.mockResolvedValue({ status: "connected" });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));
    await user.type(screen.getByLabelText(/API key/), "secret-key");
    await user.click(submitButton());

    await waitFor(() =>
      expect(api.saveConnection).toHaveBeenCalledWith("devto", {
        api_key: "secret-key",
      }),
    );
  });

  it("treats a field holding only spaces as unfilled", async () => {
    api.platforms.mockResolvedValue([platform({ credential_fields: twoFields })]);
    api.saveConnection.mockResolvedValue({ status: "connected" });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));
    await user.type(screen.getByLabelText(/API key/), "secret-key");
    await user.type(screen.getByLabelText(/Organisation/), "   ");
    await user.click(submitButton());

    await waitFor(() =>
      expect(api.saveConnection).toHaveBeenCalledWith("devto", {
        api_key: "secret-key",
      }),
    );
  });

  it("closes and re-reads the platforms once the key verifies", async () => {
    api.platforms.mockResolvedValue([platform()]);
    api.saveConnection.mockResolvedValue({ status: "connected" });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));
    await user.type(screen.getByLabelText(/API key/), "k");
    await user.click(submitButton());

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Dev.to connected"),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api.platforms).toHaveBeenCalledTimes(2);
    expect(auth.refresh).toHaveBeenCalled();
  });

  it("stays open with the typing intact when the platform rejects the key", async () => {
    api.platforms.mockResolvedValue([platform()]);
    api.saveConnection.mockRejectedValue(new Error("Credentials were rejected"));
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));
    await user.type(screen.getByLabelText(/API key/), "wrong");
    await user.click(submitButton());

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Could not connect Dev.to: Credentials were rejected"),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/API key/)).toHaveValue("wrong");
    // Re-submittable: a rejected key is the case where you retype it.
    expect(submitButton()).toBeEnabled();
  });

  it("does not reload the page's data when the save failed", async () => {
    api.platforms.mockResolvedValue([platform()]);
    api.saveConnection.mockRejectedValue(new Error("nope"));
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));
    await user.type(screen.getByLabelText(/API key/), "wrong");
    await user.click(submitButton());

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(api.platforms).toHaveBeenCalledTimes(1);
  });

  it("discards the dialog on Cancel without saving anything", async () => {
    api.platforms.mockResolvedValue([platform()]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.saveConnection).not.toHaveBeenCalled();
  });

  it("repeats the caveat where the key is actually being entered", async () => {
    api.platforms.mockResolvedValue([
      platform({ caveat: "Posts land as drafts; you publish them by hand." }),
    ]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));

    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByText("Posts land as drafts; you publish them by hand."),
    ).toBeInTheDocument();
  });
});

/**
 * The setup flow: how far along you are, what you can add next, and a dialog
 * that tells you where the key lives instead of assuming you already know.
 */
describe("account setup", () => {
  const bluesky = () =>
    platform({ platform: "bluesky", display_name: "Bluesky" });

  it("counts healthy connections against what can be connected", async () => {
    api.platforms.mockResolvedValue([
      platform({ connection: connection() }),
      bluesky(),
      platform({ platform: "twitter", display_name: "Twitter / X", implemented: false }),
    ]);
    draw();

    const progress = await screen.findByTestId("setup-progress");
    // Twitter is not buildable yet, so it is not part of the denominator.
    expect(progress).toHaveTextContent("1 of 2 accounts connected");
    expect(within(progress).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  });

  it("does not count a rejected key as connected, and says it needs a new one", async () => {
    api.platforms.mockResolvedValue([
      platform({ connection: connection({ status: "invalid" }) }),
      bluesky(),
    ]);
    draw();

    const progress = await screen.findByTestId("setup-progress");
    expect(progress).toHaveTextContent("0 of 2 accounts connected");
    expect(progress).toHaveTextContent("1 account needs a new key");
  });

  it("points a brand-new account at where to start", async () => {
    api.platforms.mockResolvedValue([platform(), bluesky()]);
    draw();

    expect(await screen.findByTestId("setup-progress")).toHaveTextContent(/No accounts yet/);
  });

  it("separates connected accounts from ones still to add", async () => {
    api.platforms.mockResolvedValue([platform({ connection: connection() }), bluesky()]);
    draw();

    expect(await screen.findByText("Your accounts")).toBeInTheDocument();
    expect(screen.getByText("Add an account")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Bluesky" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Connect Dev.to" })).not.toBeInTheDocument();
  });

  it("describes what each site is on its card", async () => {
    api.platforms.mockResolvedValue([platform()]);
    draw();

    expect(await screen.findByText("Developer community blog")).toBeInTheDocument();
  });

  it("files webhooks, API keys and health under Advanced", async () => {
    draw();

    expect(await screen.findByRole("heading", { name: "Advanced" })).toBeInTheDocument();
    expect(screen.getByText(/You don't need any of this to publish/)).toBeInTheDocument();
  });

  it("shows the steps and a direct link to where the key is made", async () => {
    api.platforms.mockResolvedValue([platform()]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("How to get your key")).toBeInTheDocument();
    const link = within(dialog).getByRole("link", { name: /Open Dev.to settings/ });
    expect(link).toHaveAttribute("href", "https://dev.to/settings/extensions");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(within(dialog).getAllByRole("listitem").length).toBeGreaterThan(1);
  });

  it("focuses the first field so the key can be pasted straight in", async () => {
    api.platforms.mockResolvedValue([platform()]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));

    expect(screen.getByLabelText(/API key/)).toHaveFocus();
  });

  it("can reveal a pasted secret to check it, and hide it again", async () => {
    api.platforms.mockResolvedValue([platform()]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));
    const input = screen.getByLabelText(/API key/);
    const toggle = within(screen.getByRole("dialog")).getByRole("button", { name: "Show" });

    await user.click(toggle);
    expect(input).toHaveAttribute("type", "text");
    expect(toggle).toHaveAttribute("aria-pressed", "true");

    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Hide" }));
    expect(input).toHaveAttribute("type", "password");
  });

  it("tucks optional non-secret settings behind a disclosure", async () => {
    api.platforms.mockResolvedValue([
      platform({
        credential_fields: [
          { key: "api_key", label: "API key", help_text: "", secret: true, required: true },
          { key: "branch", label: "Branch", help_text: "", secret: false, required: false },
          { key: "token", label: "Token", help_text: "", secret: true, required: false },
        ],
      }),
    ]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Connect Dev.to" }));

    const dialog = screen.getByRole("dialog");
    const details = dialog.querySelector("details");
    expect(details).not.toBeNull();
    expect(details).toHaveTextContent("Optional settings (1)");
    expect(details).toContainElement(screen.getByLabelText(/Branch/));
    // An optional secret changes which credential is used — it stays in view.
    expect(details).not.toContainElement(screen.getByLabelText(/Token/));
  });

  it("calls it an update when replacing a stored key", async () => {
    api.platforms.mockResolvedValue([platform({ connection: connection() })]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Replace key" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Update Dev.to" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Save new key" })).toBeInTheDocument();
  });
});

/* ---- Outbound webhooks ---- */

function webhook(overrides = {}) {
  return {
    id: 1,
    url: "https://example.com/hook",
    description: "CI notifier",
    events: ["content_published"],
    is_active: true,
    consecutive_failures: 0,
    last_delivery_at: null,
    last_status: null,
    last_error: null,
    created_at: "2025-01-15T10:00:00Z",
    ...overrides,
  };
}

describe("outbound webhooks", () => {
  it("shows the empty state when there are none", async () => {
    api.listWebhooks.mockResolvedValue([]);
    draw();

    expect(await screen.findByText("No webhooks")).toBeInTheDocument();
  });

  it("reports a failed load rather than claiming there are none", async () => {
    api.listWebhooks.mockRejectedValueOnce(new Error("Pulse did not answer"));
    api.listWebhooks.mockResolvedValueOnce([webhook()]);
    const user = userEvent.setup();
    draw();

    expect(
      await screen.findByText("Could not load webhooks: Pulse did not answer"),
    ).toBeInTheDocument();
    expect(screen.queryByText("No webhooks")).not.toBeInTheDocument();

    const banner = screen.getByText(/Could not load webhooks/).closest("[role=alert]");
    await user.click(within(banner).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(webhook().url)).toBeInTheDocument();
  });

  it("renders a webhook row with its URL and events", async () => {
    api.listWebhooks.mockResolvedValue([webhook()]);
    draw();

    expect(await screen.findByText("https://example.com/hook")).toBeInTheDocument();
    expect(screen.getByText("Content Published")).toBeInTheDocument();
    expect(screen.getByText("CI notifier")).toBeInTheDocument();
  });

  it("shows a paused badge on an inactive webhook", async () => {
    api.listWebhooks.mockResolvedValue([webhook({ is_active: false })]);
    draw();

    expect(await screen.findByText("paused")).toBeInTheDocument();
  });

  it("shows a failure badge when consecutive failures > 0", async () => {
    api.listWebhooks.mockResolvedValue([webhook({ consecutive_failures: 3 })]);
    draw();

    expect(await screen.findByText("3 failures")).toBeInTheDocument();
  });

  it("shows the last error when present", async () => {
    api.listWebhooks.mockResolvedValue([
      webhook({ last_error: "Connection refused" }),
    ]);
    draw();

    expect(await screen.findByText("Connection refused")).toBeInTheDocument();
  });

  it("lists recent deliveries on demand, and redelivers a failed one", async () => {
    const delivery = (overrides) => ({
      id: 1, webhook_id: 1, event: "content.published", status: "delivered", attempts: 1,
      response_status: 200, error: null, created_at: "2026-08-01T10:00:00Z", payload: {},
      ...overrides,
    });
    api.listWebhooks.mockResolvedValue([webhook()]);
    api.webhookDeliveries.mockResolvedValue([
      delivery({ id: 7, status: "failed", response_status: 503, error: "Returned 503" }),
      delivery({ id: 6 }),
    ]);
    api.redeliverWebhook.mockResolvedValue(delivery({ id: 8 }));
    const user = userEvent.setup();
    draw();

    const toggle = await screen.findByRole("button", { name: "Recent deliveries" });
    // Nothing is fetched until somebody asks.
    expect(api.webhookDeliveries).not.toHaveBeenCalled();
    await user.click(toggle);

    expect(await screen.findByText("Returned 503")).toBeInTheDocument();
    // Only the failed one offers to go again.
    const redeliver = screen.getAllByRole("button", { name: "Redeliver" });
    expect(redeliver).toHaveLength(1);
    await user.click(redeliver[0]);

    expect(api.redeliverWebhook).toHaveBeenCalledWith(webhook().id, 7);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Redelivered"));
  });

  it("pings a webhook and shows success", async () => {
    api.listWebhooks.mockResolvedValue([webhook()]);
    api.pingWebhook.mockResolvedValue({ status: "delivered" });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Ping" }));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Ping delivered"),
    );
  });

  it("pings a webhook and shows failure", async () => {
    api.listWebhooks.mockResolvedValue([webhook()]);
    api.pingWebhook.mockResolvedValue({ status: "failed", error: "timeout" });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Ping" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("timeout"));
  });

  it("pauses and resumes a webhook", async () => {
    api.listWebhooks.mockResolvedValue([webhook()]);
    api.updateWebhook.mockResolvedValue({});
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Pause" }));
    await waitFor(() =>
      expect(api.updateWebhook).toHaveBeenCalledWith(1, { is_active: false }),
    );
    expect(toast.success).toHaveBeenCalledWith("Paused");
  });

  it("deletes a webhook after confirmation", async () => {
    api.listWebhooks.mockResolvedValue([webhook()]);
    api.deleteWebhook.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.deleteWebhook).toHaveBeenCalledWith(1));
    expect(toast.success).toHaveBeenCalledWith("Webhook deleted");
    window.confirm.mockRestore();
  });

  it("says the event list failed to load in the create dialog, with Retry", async () => {
    api.listWebhooks.mockResolvedValue([]);
    api.webhookEvents.mockRejectedValueOnce(new Error("offline"));
    api.webhookEvents.mockResolvedValueOnce([
      { event: "content_published", description: "A piece went live." },
    ]);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Add webhook" }));
    const dialog = screen.getByRole("dialog");

    expect(await within(dialog).findByText(/Could not load the event list/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Retry" }));
    expect(await within(dialog).findByText("Content Published")).toBeInTheDocument();
  });

  it("opens the create dialog and submits a new webhook", async () => {
    api.listWebhooks.mockResolvedValue([]);
    api.webhookEvents.mockResolvedValue([
      { event: "content_published", description: "A piece went live." },
      { event: "publication_failed", description: "A platform gave up." },
    ]);
    api.createWebhook.mockResolvedValue({
      ...webhook(),
      secret: "whsec_test123",
    });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Add webhook" }));

    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Endpoint URL"), "https://hook.test/cb");
    await user.click(within(dialog).getByText("Content Published"));
    await user.click(within(dialog).getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(api.createWebhook).toHaveBeenCalledWith({
        url: "https://hook.test/cb",
        events: ["content_published"],
        description: "",
      }),
    );

    // The one-time secret dialog should appear
    expect(await screen.findByText("Signing secret")).toBeInTheDocument();
    expect(screen.getByDisplayValue("whsec_test123")).toBeInTheDocument();
  });
});

/* ---- API keys ---- */

function apiKey(overrides = {}) {
  return {
    id: 1,
    project_id: 1,
    name: "CI deploy key",
    prefix: "psk_abc",
    scopes: ["content_read"],
    expires_at: null,
    revoked_at: null,
    last_used_at: null,
    rotated_from_id: null,
    created_at: "2025-01-20T10:00:00Z",
    ...overrides,
  };
}

describe("API keys", () => {
  it("shows the empty state when there are none", async () => {
    api.listApiKeys.mockResolvedValue([]);
    draw();

    expect(await screen.findByText("No API keys")).toBeInTheDocument();
  });

  it("reports a failed load rather than claiming there are none", async () => {
    api.listApiKeys.mockRejectedValueOnce(new Error("Pulse did not answer"));
    draw();

    expect(
      await screen.findByText("Could not load API keys: Pulse did not answer"),
    ).toBeInTheDocument();
    expect(screen.queryByText("No API keys")).not.toBeInTheDocument();
  });

  it("renders a key row with its name, prefix, and scopes", async () => {
    api.listApiKeys.mockResolvedValue([apiKey()]);
    draw();

    expect(await screen.findByText("CI deploy key")).toBeInTheDocument();
    expect(screen.getByText("psk_abc…")).toBeInTheDocument();
    expect(screen.getByText("Content Read")).toBeInTheDocument();
  });

  it("shows a revoked badge on a revoked key", async () => {
    api.listApiKeys.mockResolvedValue([
      apiKey({ revoked_at: "2025-02-01T10:00:00Z" }),
    ]);
    draw();

    expect(await screen.findByText("revoked")).toBeInTheDocument();
    // No revoke button for an already-revoked key
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
  });

  it("revokes a key after confirmation", async () => {
    api.listApiKeys.mockResolvedValue([apiKey()]);
    api.revokeApiKey.mockResolvedValue({ ...apiKey(), revoked_at: "2025-02-01T10:00:00Z" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(api.revokeApiKey).toHaveBeenCalledWith(1));
    expect(toast.success).toHaveBeenCalledWith("Key revoked");
    window.confirm.mockRestore();
  });

  it("says the scope list failed to load in the create dialog", async () => {
    api.listApiKeys.mockResolvedValue([]);
    api.listProjects.mockResolvedValue([{ id: 1, name: "My Project" }]);
    api.apiKeyScopes.mockRejectedValue(new Error("offline"));
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Create key" }));
    const dialog = screen.getByRole("dialog");

    expect(await within(dialog).findByText(/Could not load the scope list/)).toBeInTheDocument();
  });

  it("opens the create dialog and mints a key", async () => {
    api.listApiKeys.mockResolvedValue([]);
    api.listProjects.mockResolvedValue([{ id: 1, name: "My Project" }]);
    api.apiKeyScopes.mockResolvedValue([
      { scope: "content_read", description: "List the project's pieces." },
      { scope: "content_write", description: "File an idea." },
    ]);
    api.createApiKey.mockResolvedValue({
      ...apiKey(),
      token: "psk_abc.secret_token_value",
    });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Create key" }));

    const dialog = screen.getByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Project"), "1");
    await user.type(within(dialog).getByLabelText("Key name"), "CI deploy key");
    await user.click(within(dialog).getByText("Content Read"));
    await user.click(within(dialog).getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(api.createApiKey).toHaveBeenCalledWith({
        project_id: 1,
        name: "CI deploy key",
        scopes: ["content_read"],
        expires_in_days: null,
      }),
    );

    // The one-time token dialog should appear
    expect(await screen.findByText("API token")).toBeInTheDocument();
    expect(screen.getByDisplayValue("psk_abc.secret_token_value")).toBeInTheDocument();
  });
});

/* ---- Personal AI key ---- */

describe("your AI key", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function form() {
    return screen.getByRole("form", { name: "AI key" });
  }

  it("offers the form with Gemini picked and a link to get a key", async () => {
    draw();

    expect(await screen.findByRole("heading", { name: "Your AI key" })).toBeInTheDocument();
    const select = await within(await screen.findByRole("form", { name: "AI key" })).findByLabelText("Provider");
    expect(select).toHaveValue("gemini");
    expect(screen.getByRole("link", { name: /Get a Google Gemini key/ })).toHaveAttribute(
      "href",
      "https://aistudio.google.com/app/apikey",
    );
  });

  it("switches the key link with the provider", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByRole("form", { name: "AI key" });

    await user.selectOptions(within(form()).getByLabelText("Provider"), "openai");

    expect(screen.getByRole("link", { name: /Get a OpenAI key/ })).toHaveAttribute(
      "href",
      "https://platform.openai.com/api-keys",
    );
  });

  it("keeps Save disabled until something key-shaped is typed", async () => {
    const user = userEvent.setup();
    draw();
    await screen.findByRole("form", { name: "AI key" });
    const save = within(form()).getByRole("button", { name: "Save key" });

    expect(save).toBeDisabled();
    await user.type(within(form()).getByLabelText(/Your key/), "AIzaSy-123456");
    expect(save).toBeEnabled();
  });

  it("saves the provider, trimmed key and blank model, then reloads", async () => {
    api.saveLlmKey.mockResolvedValue({ providers: LLM_PROVIDERS, key: null });
    const user = userEvent.setup();
    draw();
    await screen.findByRole("form", { name: "AI key" });

    await user.type(within(form()).getByLabelText(/Your key/), "  AIzaSy-123456  ");
    await user.click(within(form()).getByRole("button", { name: "Save key" }));

    await waitFor(() =>
      expect(api.saveLlmKey).toHaveBeenCalledWith({
        provider: "gemini",
        api_key: "AIzaSy-123456",
        model: "",
      }),
    );
    expect(toast.success).toHaveBeenCalledWith(
      "Google Gemini key saved — Pulse will use it from now on",
    );
    await waitFor(() => expect(api.llmKey).toHaveBeenCalledTimes(2));
  });

  it("says why when the provider refuses the key", async () => {
    api.saveLlmKey.mockRejectedValue(new Error("The key did not work: API key not valid"));
    const user = userEvent.setup();
    draw();
    await screen.findByRole("form", { name: "AI key" });

    await user.type(within(form()).getByLabelText(/Your key/), "AIzaSy-wrong-key");
    await user.click(within(form()).getByRole("button", { name: "Save key" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Could not save the AI key: The key did not work: API key not valid",
      ),
    );
    expect(within(form()).getByLabelText(/Your key/)).toHaveValue("AIzaSy-wrong-key");
  });

  it("shows a stored key by its hint only, with the default model named", async () => {
    api.llmKey.mockResolvedValue({
      providers: LLM_PROVIDERS,
      key: {
        provider: "gemini",
        model: "",
        key_hint: "abcd",
        last_verified_at: null,
        last_error: null,
      },
    });
    draw();

    expect(await screen.findByText("Google Gemini")).toBeInTheDocument();
    expect(screen.getByText("in use")).toBeInTheDocument();
    expect(screen.getByText(/key …abcd · gemini-flash-latest \(default\)/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "AI key" })).not.toBeInTheDocument();
  });

  it("can change a stored key, and cancel back out", async () => {
    api.llmKey.mockResolvedValue({
      providers: LLM_PROVIDERS,
      key: { provider: "openai", model: "gpt-4o", key_hint: "wxyz" },
    });
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Change key" }));
    expect(within(form()).getByLabelText("Provider")).toHaveValue("openai");

    await user.click(within(form()).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "AI key" })).not.toBeInTheDocument();
  });

  it("removes a stored key after asking", async () => {
    api.llmKey.mockResolvedValue({
      providers: LLM_PROVIDERS,
      key: { provider: "gemini", model: "", key_hint: "abcd" },
    });
    api.deleteLlmKey.mockResolvedValue(null);
    const confirm = vi.fn().mockReturnValue(true);
    vi.stubGlobal("confirm", confirm);
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Remove" }));

    expect(confirm).toHaveBeenCalled();
    await waitFor(() => expect(api.deleteLlmKey).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith("AI key removed");
  });
});

describe("deleting the account", () => {
  async function openDialog(user) {
    draw();
    await user.click(await screen.findByRole("button", { name: "Delete my account…" }));
    return screen.findByRole("dialog", { name: "Delete account" });
  }

  it("says what goes, and what cannot be reached", async () => {
    draw();
    expect(await screen.findByText(/Posts already published to other platforms stay there/)).toBeInTheDocument();
  });

  it("asks for the password before anything is deleted", async () => {
    const user = userEvent.setup();
    await openDialog(user);
    expect(screen.getByRole("button", { name: "Delete everything" })).toBeDisabled();
    expect(api.deleteAccount).not.toHaveBeenCalled();
  });

  it("deletes, signs out and leaves for the front page", async () => {
    api.deleteAccount.mockResolvedValue(null);
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    try {
      const user = userEvent.setup();
      await openDialog(user);
      await user.type(screen.getByLabelText("Password"), "hunter2hunter2");
      await user.click(screen.getByRole("button", { name: "Delete everything" }));
      await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
      expect(api.deleteAccount).toHaveBeenCalledWith("hunter2hunter2");
      expect(auth.logout).toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("keeps the dialog open with the reason when the password is wrong", async () => {
    api.deleteAccount.mockRejectedValue(
      Object.assign(new Error("That password is not right, so nothing was deleted."), { status: 403 }),
    );
    const user = userEvent.setup();
    await openDialog(user);
    await user.type(screen.getByLabelText("Password"), "nope");
    await user.click(screen.getByRole("button", { name: "Delete everything" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("nothing was deleted");
    expect(auth.logout).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Delete account" })).toBeInTheDocument();
  });
});

describe("downloading your work", () => {
  it("saves the export as a dated JSON file and says how much was in it", async () => {
    api.exportAccount.mockResolvedValue({
      format_version: 1, projects: [{ id: 1 }], content: [{ id: 1 }, { id: 2 }],
      templates: [], ideas: [], account: {}, exported_at: "2026-10-28T00:00:00Z",
    });
    const createObjectURL = vi.fn(() => "blob:export");
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Download my data" }));

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Exported 2 pieces from 1 projects"),
    );
    expect(clicked).toHaveBeenCalled();
    expect(clicked.mock.contexts[0].download).toMatch(/^pulse-export-\d{4}-\d{2}-\d{2}\.json$/);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:export");
    clicked.mockRestore();
  });

  it("reports an export that failed", async () => {
    api.exportAccount.mockRejectedValue(new Error("Too many requests"));
    const user = userEvent.setup();
    draw();

    await user.click(await screen.findByRole("button", { name: "Download my data" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Could not export: Too many requests"),
    );
  });
});

