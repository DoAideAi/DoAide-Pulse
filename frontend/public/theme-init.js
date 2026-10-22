// Applies the saved theme before first paint. A file rather than an inline
// <script> because the SPA's CSP is script-src 'self' with no 'unsafe-inline'
// — inline, this was blocked and every dark-mode user got a light flash.
(function () {
  var s = null;
  try {
    s = localStorage.getItem("pulse-theme");
  } catch (e) {}
  var d = s === "dark" || (s === "system" && matchMedia("(prefers-color-scheme:dark)").matches);
  if (d) document.documentElement.classList.add("dark");
  var m = document.querySelector('meta[name="theme-color"]');
  if (m) m.content = d ? "#0A0A0B" : "#FFFFFF";
  var c = document.querySelector('meta[name="color-scheme"]');
  if (c) c.content = d ? "dark" : "light";
})();
