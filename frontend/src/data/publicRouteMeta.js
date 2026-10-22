/**
 * Title and description for every public route that is not a blog post.
 *
 * One table read twice: by each page's `usePageMeta`, and by the build, which
 * writes a copy of index.html per route with these tags already in it. A
 * crawler or link unfurler that does not run JavaScript — WhatsApp, LinkedIn,
 * Slack, X — reads only that static head, and before this every one of them
 * saw the homepage's title and canonical on every shared link.
 *
 * Plain data, no JSX and no browser globals: `vite.config.js` imports it.
 */
export const PUBLIC_ROUTE_META = {
  "/": {
    title: "DoAide Pulse — AI Newsletter Platform for Indian Businesses",
    description:
      "Create, publish, and grow AI-powered newsletters. Research, write, and optimize — all automated. Built for Indian businesses with multilingual support.",
    path: "/",
  },
  "/blog": {
    title: "Blog — Newsletter Tips & Email Marketing Strategies | DoAide Pulse",
    description:
      "Expert articles on email marketing, newsletter best practices, AI content creation, and subscriber growth strategies for Indian businesses.",
    path: "/blog",
  },
  "/embed": {
    title: "Embed Widget Generator | DoAide Pulse",
    description:
      "Generate a free embeddable newsletter signup widget for your website. Pick a colour and layout, copy the code — no login required.",
    path: "/embed",
  },
  "/gallery": {
    title: "Newsletter Gallery | DoAide Pulse",
    description:
      "Explore AI-generated newsletter examples across industries — technology, startups, design, e-commerce, engineering, and lifestyle. See what DoAide Pulse can create.",
    path: "/gallery",
  },
  "/templates": {
    title: "Free Newsletter Templates | DoAide Pulse",
    description:
      "Browse free newsletter templates for marketing, product updates, digests, announcements, tutorials, and community roundups. Customize and send with DoAide Pulse.",
    path: "/templates",
  },
  "/tools/newsletter-roi-calculator": {
    title: "Newsletter ROI Calculator | DoAide Pulse",
    description:
      "Estimate the revenue and return on your newsletter from subscribers, open, click and conversion rates. Free, no signup.",
    path: "/tools/newsletter-roi-calculator",
  },
  "/tools/content-idea-generator": {
    title: "Free Content Idea Generator | DoAide Pulse",
    description:
      "Generate fresh content ideas for your newsletter or blog with AI. Free, no login required. Powered by DoAide Pulse.",
    path: "/tools/content-idea-generator",
  },
  "/tools/subject-line-tester": {
    title: "Subject Line Tester | DoAide Pulse",
    description:
      "Score your email subject line on open-rate predictors — length, urgency, personalisation, spam words. Free, no signup.",
    path: "/tools/subject-line-tester",
  },
  "/tools/send-time-optimizer": {
    title: "Send Time Optimizer | DoAide Pulse",
    description:
      "Find the best day and hour to send your newsletter for your industry and time zone. Free, no signup.",
    path: "/tools/send-time-optimizer",
  },
};
