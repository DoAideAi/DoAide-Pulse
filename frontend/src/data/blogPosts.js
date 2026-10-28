import { blogPostIndex } from "./blogPostIndex.js";
import post_how_to_start_email_newsletter_2026 from "./posts/how-to-start-email-newsletter-2026.js";
import post_free_seo_tools_india_2026 from "./posts/free-seo-tools-india-2026.js";
import post_how_to_improve_website_seo from "./posts/how-to-improve-website-seo.js";
import post_best_ai_newsletter_platforms_2026 from "./posts/best-ai-newsletter-platforms-2026.js";
import post_email_marketing_india_complete_guide_2026 from "./posts/email-marketing-india-complete-guide-2026.js";
import post_content_curation_tools_newsletters_2026 from "./posts/content-curation-tools-newsletters-2026.js";
import post_subject_lines_40_percent_open_rates from "./posts/subject-lines-40-percent-open-rates.js";
import post_newsletter_0_to_10000_indian_creator_playbook from "./posts/newsletter-0-to-10000-indian-creator-playbook.js";
import post_email_deliverability_guide_avoid_spam_2026 from "./posts/email-deliverability-guide-avoid-spam-2026.js";
import post_free_ai_gst_compliance_tool_indian_businesses from "./posts/free-ai-gst-compliance-tool-indian-businesses.js";
import post_digital_toolkit_every_lic_agent_needs from "./posts/digital-toolkit-every-lic-agent-needs.js";
import post_file_itr_minutes_with_ai from "./posts/file-itr-minutes-with-ai.js";
import post_generate_professional_documents_instantly from "./posts/generate-professional-documents-instantly.js";
import post_build_ats_optimized_resumes_free from "./posts/build-ats-optimized-resumes-free.js";
import post_ai_newsletters_3x_engagement from "./posts/ai-newsletters-3x-engagement.js";
import post_subject_line_formulas_open_rates from "./posts/subject-line-formulas-open-rates.js";
import post_guide_newsletter_that_converts from "./posts/guide-newsletter-that-converts.js";
import post_email_marketing_strategies_indian_businesses from "./posts/email-marketing-strategies-indian-businesses.js";
import post_ai_content_creation_newsletter_automation from "./posts/ai-content-creation-newsletter-automation.js";
import post_newsletter_best_practices_2026 from "./posts/newsletter-best-practices-2026.js";
import post_growing_newsletter_subscribers_organically from "./posts/growing-newsletter-subscribers-organically.js";
import post_best_free_newsletter_tools_india_2026 from "./posts/best-free-newsletter-tools-india-2026.js";
import post_grow_email_subscribers_0_to_1000 from "./posts/grow-email-subscribers-0-to-1000.js";
import post_email_marketing_vs_social_media_marketing from "./posts/email-marketing-vs-social-media-marketing.js";

/**
 * Each post's body and FAQs, keyed by slug. Listings live in blogPostIndex.js.
 *
 * One module per post, under ./posts, so the /blog/:slug page can load the one
 * being read (see pages/BlogPost.jsx) instead of every post's full text — this
 * file held all of them, and importing it made a single post view download
 * about 125 KB of other posts. This module still gathers them for the build's
 * prerender (vite.config.js) and the tests, which want every post at once.
 */
export const POST_CONTENT = {
  "how-to-start-email-newsletter-2026": post_how_to_start_email_newsletter_2026,
  "free-seo-tools-india-2026": post_free_seo_tools_india_2026,
  "how-to-improve-website-seo": post_how_to_improve_website_seo,
  "best-ai-newsletter-platforms-2026": post_best_ai_newsletter_platforms_2026,
  "email-marketing-india-complete-guide-2026": post_email_marketing_india_complete_guide_2026,
  "content-curation-tools-newsletters-2026": post_content_curation_tools_newsletters_2026,
  "subject-lines-40-percent-open-rates": post_subject_lines_40_percent_open_rates,
  "newsletter-0-to-10000-indian-creator-playbook": post_newsletter_0_to_10000_indian_creator_playbook,
  "email-deliverability-guide-avoid-spam-2026": post_email_deliverability_guide_avoid_spam_2026,
  "free-ai-gst-compliance-tool-indian-businesses": post_free_ai_gst_compliance_tool_indian_businesses,
  "digital-toolkit-every-lic-agent-needs": post_digital_toolkit_every_lic_agent_needs,
  "file-itr-minutes-with-ai": post_file_itr_minutes_with_ai,
  "generate-professional-documents-instantly": post_generate_professional_documents_instantly,
  "build-ats-optimized-resumes-free": post_build_ats_optimized_resumes_free,
  "ai-newsletters-3x-engagement": post_ai_newsletters_3x_engagement,
  "subject-line-formulas-open-rates": post_subject_line_formulas_open_rates,
  "guide-newsletter-that-converts": post_guide_newsletter_that_converts,
  "email-marketing-strategies-indian-businesses": post_email_marketing_strategies_indian_businesses,
  "ai-content-creation-newsletter-automation": post_ai_content_creation_newsletter_automation,
  "newsletter-best-practices-2026": post_newsletter_best_practices_2026,
  "growing-newsletter-subscribers-organically": post_growing_newsletter_subscribers_organically,
  "best-free-newsletter-tools-india-2026": post_best_free_newsletter_tools_india_2026,
  "grow-email-subscribers-0-to-1000": post_grow_email_subscribers_0_to_1000,
  "email-marketing-vs-social-media-marketing": post_email_marketing_vs_social_media_marketing,
};

/** Every post in full, in the index's order. */
export const staticPosts = blogPostIndex.map((post) => ({ ...post, ...POST_CONTENT[post.slug] }));
