import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { blogPostIndex } from "./blogPostIndex";
import { POST_CONTENT, staticPosts } from "./blogPosts";

describe("blog data", () => {
  it("has a body for every listed post, and no body without a listing", () => {
    const listed = blogPostIndex.map((p) => p.slug);
    expect(new Set(listed).size).toBe(listed.length);
    expect(Object.keys(POST_CONTENT).sort()).toEqual([...listed].sort());
    for (const post of staticPosts) expect(post.body.length).toBeGreaterThan(0);
  });

  it("keeps bodies out of what the /blog listing downloads", () => {
    for (const post of blogPostIndex) {
      expect(post).not.toHaveProperty("body");
      expect(post).not.toHaveProperty("faqs");
    }
    // The listing imports the index, never the full posts.
    const blog = readFileSync(resolve(__dirname, "../pages/Blog.jsx"), "utf8");
    expect(blog).toContain('from "../data/blogPostIndex"');
    expect(blog).not.toMatch(/from "\.\.\/data\/blogPosts"/);
  });

  it("claims no research Pulse never did", () => {
    // The posts quoted "our data across 50,000 campaigns" and "after analyzing
    // over 500,000 email campaigns" — studies nobody ran, with open rates
    // attached. Advice is fine; an invented dataset presented as ours is not.
    const invented =
      /\b(our (data|dataset|analysis|research|study)|we (found|studied|analy[sz]ed|surveyed|measured)|after (studying|analy[sz]ing))\b|\b[0-9]{2,3},000 (email )?campaigns\b/i;
    for (const post of staticPosts) {
      const text = [post.description, ...post.body, ...(post.faqs ?? []).flatMap((f) => [f.q, f.a, f.question, f.answer])]
        .filter(Boolean)
        .join(" ");
      expect(text, post.slug).not.toMatch(invented);
    }
  });
});
