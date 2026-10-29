// The one copy of the backend's content enums the app keeps.
//
// There used to be two: the content list had its own, and lib/triggers.js had
// another that called itself a mirror of `ContentType` and was missing
// `product_spotlight` — so a trigger or a template could not be set to write
// one. backend/tests/test_the_frontend_offers_every_content_type.py compares
// these with the enums and fails on any second copy.

/** `ContentType`, in the order the pickers list them. */
export const CONTENT_TYPES = [
  "announcement",
  "tutorial",
  "feature_spotlight",
  "product_spotlight",
  "comparison",
  "how_to",
  "social_thread",
  "changelog",
];

/** `ContentStatus`, in the order a piece moves through them. */
export const CONTENT_STATUSES = ["draft", "review", "approved", "published", "failed", "archived"];
