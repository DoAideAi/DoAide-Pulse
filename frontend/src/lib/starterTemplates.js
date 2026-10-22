// Quick-start templates for the three cadences most people post on.
//
// Shaped like a template from the API minus the `id`, so the editor opens on
// one exactly as it opens on a saved template — and saving creates a new one
// rather than overwriting anything. Every placeholder is either a built-in
// (`app/services/templates.py` BUILTINS) or declared in `variables`; the test
// pins that so a renamed built-in cannot leave a starter the server rejects.

export const STARTER_TEMPLATES = [
  {
    key: "weekly",
    cadence: "Weekly",
    name: "Weekly check-in",
    description: "What shipped this week, in a few lines. Short enough to post every Friday.",
    mode: "prompt",
    content_type: "changelog",
    title_template: "This week in {{project.name}} — {{date.long}}",
    body_template: `Write a short weekly update for {{project.name}} ({{project.url}}).

What changed this week:
{{signal.items}}

Anything else worth mentioning: {{highlight}}

Keep it under 250 words. Lead with the change a user would notice first, one line per item after that, and end with where to try it.`,
    variables: [
      {
        name: "highlight",
        label: "Highlight",
        description: "One thing you want called out, even if it isn't in the commits.",
        default: "",
        required: false,
      },
    ],
    default_project_id: null,
  },
  {
    key: "monthly",
    cadence: "Monthly",
    name: "Monthly roundup",
    description: "The month's releases grouped by theme, with the one number that moved.",
    mode: "prompt",
    content_type: "announcement",
    title_template: "{{project.name}} in {{date.month}} {{date.year}}",
    body_template: `Write a monthly roundup for {{project.name}}: {{project.description}}

Changes this month:
{{signal.items}}

The metric that moved: {{metric}}

Group the changes into two or three themes rather than listing them in order. Open with the theme that matters most to {{audience}}. 400–600 words, with a heading per theme.`,
    variables: [
      {
        name: "metric",
        label: "Metric",
        description: "e.g. \"signups up 30%\" or \"p95 latency down to 180ms\".",
        default: "",
        required: false,
      },
      {
        name: "audience",
        label: "Audience",
        description: "Who the roundup is written for.",
        default: "existing users",
        required: false,
      },
    ],
    default_project_id: null,
  },
  {
    key: "quarterly",
    cadence: "Quarterly",
    name: "Quarterly review",
    description: "Look back on the quarter, say what you learned, and what's next.",
    mode: "prompt",
    content_type: "feature_spotlight",
    title_template: "{{project.name}}: the quarter in review",
    body_template: `Write a quarterly review for {{project.name}} ({{project.tech_stack}}).

Biggest wins: {{wins}}
What didn't work: {{lessons}}
Next quarter: {{next}}

Be candid about what didn't work — it is the part readers trust. 700–1000 words, three sections (Shipped, Learned, Next), and end with a link to {{project.url}}.`,
    variables: [
      {
        name: "wins",
        label: "Wins",
        description: "The two or three things you're proudest of.",
        default: "",
        required: true,
      },
      {
        name: "lessons",
        label: "Lessons",
        description: "What you'd do differently.",
        default: "",
        required: false,
      },
      {
        name: "next",
        label: "Next",
        description: "What the next quarter is for.",
        default: "",
        required: true,
      },
    ],
    default_project_id: null,
  },
];
