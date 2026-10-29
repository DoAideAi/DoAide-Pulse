import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // What vite.config.js fills with the commit being built (see there).
  define: { __PULSE_RELEASE__: JSON.stringify("test-release") },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
    coverage: {
      provider: "v8",
      // `src` only. The two config files at the root are build inputs Vite
      // reads and no test imports, so counting them dragged the headline
      // figure down by a point and a half for no coverable line.
      include: ["src/**/*.{js,jsx}"],
      // The test helpers cover themselves by being used; reporting on them
      // says nothing about the app.
      exclude: ["src/**/*.test.{js,jsx}", "src/test/**"],
      reporter: ["text", "html"],
      // These numbers once read 99/99/99/98, beside a note that `src` was at
      // 100%. CI never ran with --coverage, so nothing checked them, and by the
      // first run that did (Pass 38 M20) the suite stood at 93.29% lines,
      // 92.61% statements, 92.48% functions and 90.16% branches. A gate set
      // above the truth is red on every push and stops being read, so it now
      // sits just under where the suite really is. It stops any further slide
      // today; raise it as the untested code gets tests, and keep the slack
      // thin — a floor two points under the suite lets two points rot first.
      thresholds: {
        statements: 92,
        lines: 93,
        functions: 92,
        branches: 90,
      },
    },
  },
});
