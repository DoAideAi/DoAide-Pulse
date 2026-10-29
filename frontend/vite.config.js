import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { execSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { PUBLIC_ROUTE_META } from "./src/data/publicRouteMeta.js";
import { staticPosts } from "./src/data/blogPosts.js";
import { prerenderRoutes, withPageMeta } from "./src/lib/prerenderHead.js";

/**
 * After the build, write `dist/<route>/index.html` for each public route with
 * that route's title, description and canonical in the static head. See
 * `src/lib/prerenderHead.js` for why.
 */
function prerenderHeads() {
  let outDir;
  return {
    name: "pulse-prerender-heads",
    apply: "build",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    closeBundle() {
      const shell = readFileSync(join(outDir, "index.html"), "utf-8");
      for (const meta of prerenderRoutes(PUBLIC_ROUTE_META, staticPosts)) {
        const file = join(outDir, meta.path, "index.html");
        mkdirSync(dirname(file), { recursive: true });
        writeFileSync(file, withPageMeta(shell, meta));
      }
    },
  };
}

/**
 * The commit being built, short form — what a crash report names as its
 * `release` (src/lib/clientErrors.js), so the journal says which deploy's
 * bundle crashed. Empty outside a git checkout rather than failing the build.
 */
function release() {
  try {
    return execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return "";
  }
}

// Proxy /api to the FastAPI backend during development.
export default defineConfig({
  plugins: [react(), prerenderHeads()],
  define: { __PULSE_RELEASE__: JSON.stringify(release()) },
  build: {
    rollupOptions: {
      output: {
        // React and the router change far less often than the app does, so
        // they get a chunk of their own that stays cached across deploys.
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
