/**
 * Where to get the key for each publishing platform, in plain steps.
 *
 * The adapter's own `help_text` is one terse breadcrumb per field — enough
 * for someone who has done this before, not for someone connecting their
 * first account. This adds the missing part: a link straight to the page
 * that mints the key, and the two or three clicks once there.
 *
 * A platform missing from here still connects; it just gets the generic
 * guide, so a new adapter never blocks on a docs change.
 */

export const PLATFORM_GUIDES = {
  devto: {
    tagline: "Developer community blog",
    setupUrl: "https://dev.to/settings/extensions",
    steps: [
      "Open DEV → Settings → Extensions.",
      "Under “DEV Community API Keys”, name a key (e.g. Pulse) and click Generate.",
      "Copy the key and paste it below.",
    ],
  },
  hashnode: {
    tagline: "Developer blog on your own domain",
    setupUrl: "https://hashnode.com/settings/developer",
    steps: [
      "Open Hashnode → Account settings → Developer.",
      "Generate a new Personal Access Token and copy it.",
      "Open your blog dashboard — the publication ID is the long string in its URL.",
    ],
  },
  medium: {
    tagline: "General-audience publishing",
    setupUrl: "https://medium.com/me/settings/security",
    steps: [
      "Open Medium → Settings → Security and apps.",
      "Under Integration tokens, enter a description (e.g. Pulse) and click Get token.",
      "Copy the token and paste it below.",
    ],
  },
  wordpress: {
    tagline: "Your self-hosted or WordPress.com blog",
    setupUrl: null,
    steps: [
      "Sign in to your WordPress admin and open Users → Profile.",
      "Scroll to Application Passwords, name one Pulse and click Add.",
      "Copy the generated password — not your login password — and paste it below with your site URL and username.",
    ],
  },
  mastodon: {
    tagline: "Fediverse posts from your account",
    setupUrl: null,
    steps: [
      "On your Mastodon server, open Preferences → Development → New application.",
      "Name it Pulse and tick write:statuses and read:accounts.",
      "Save, open the application and copy “Your access token”.",
    ],
  },
  bluesky: {
    tagline: "Short posts to your Bluesky handle",
    setupUrl: "https://bsky.app/settings/app-passwords",
    steps: [
      "Open Bluesky → Settings → Privacy and security → App passwords.",
      "Add an app password named Pulse and copy it.",
      "Paste it below with your handle (e.g. you.bsky.social).",
    ],
  },
  buttondown: {
    tagline: "Email newsletter",
    setupUrl: "https://buttondown.com/settings/programming",
    steps: [
      "Open Buttondown → Settings → Programming.",
      "Copy your API key and paste it below.",
    ],
  },
  git: {
    tagline: "Commit Markdown to your blog's repo",
    setupUrl: "https://github.com/settings/personal-access-tokens/new",
    steps: [
      "Create a fine-grained GitHub token for the blog's repository with Contents: Read and write.",
      "Enter the repository as owner/name and paste the token below.",
      "Optional: set the branch, post path and site URL if your setup differs from the defaults.",
    ],
  },
  linkedin: {
    tagline: "Professional network posts",
    setupUrl: null,
    steps: [],
  },
  twitter: {
    tagline: "Short posts and threads",
    setupUrl: null,
    steps: [],
  },
};

/** The guide for one platform, falling back to a generic one. */
export function guideFor(platform) {
  const known = PLATFORM_GUIDES[platform?.platform];
  if (known) return known;
  return {
    tagline: "",
    setupUrl: null,
    steps: [
      `Sign in to ${platform?.display_name ?? "the platform"} and create an API key or token.`,
      "Paste it below — Pulse checks it before saving.",
    ],
  };
}

/**
 * Split the platform list into what the settings page shows as groups.
 *
 * `attention` is connections the platform has stopped accepting: they are
 * listed with the connected ones but counted separately, because "3 of 8
 * connected" with one of the three silently broken is the number that lies.
 */
export function groupPlatforms(platforms) {
  const list = platforms ?? [];
  const connected = list.filter((p) => p.connection);
  const available = list.filter((p) => !p.connection && p.implemented);
  const comingSoon = list.filter((p) => !p.connection && !p.implemented);
  const attention = connected.filter((p) => p.connection.status !== "connected");
  return {
    connected,
    available,
    comingSoon,
    attention,
    // Coming-soon platforms are not something you can set up, so they do not
    // count towards the total you are being asked to complete.
    total: connected.length + available.length,
    healthy: connected.length - attention.length,
  };
}
