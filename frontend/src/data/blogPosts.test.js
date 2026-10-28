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
});
