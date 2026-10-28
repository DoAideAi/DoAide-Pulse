(function () {
  "use strict";

  var DEFAULT_COLOR = "#F0B429";

  // Only a hex colour is used. The value is the host page's markup, but it is
  // concatenated into style strings, and anything else either broke the
  // widget's styling silently or, in the link's style attribute, became markup.
  function hexColor(value) {
    var v = (value || "").trim();
    var m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(v);
    if (!m) return DEFAULT_COLOR;
    var hex = m[1];
    if (hex.length === 3) {
      hex = hex.charAt(0) + hex.charAt(0) + hex.charAt(1) + hex.charAt(1) + hex.charAt(2) + hex.charAt(2);
    }
    return "#" + hex.toUpperCase();
  }

  // Dark text on a light accent, white on a dark one — a navy button with
  // near-black text was unreadable.
  function textOn(hex) {
    var n = parseInt(hex.slice(1), 16);
    var rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(function (c) {
      c /= 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    var lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
    return lum > 0.179 ? "#0A0A0B" : "#FFFFFF";
  }

  var API_BASE = (function () {
    var scripts = document.querySelectorAll("script[src*='embed.js']");
    if (scripts.length) {
      var src = scripts[scripts.length - 1].src;
      return src.replace(/\/embed\.js.*$/, "/api/v1");
    }
    return "https://pulse.doaide.com/api/v1";
  })();

  function mount(el) {
    // Pasting the snippet twice, or a page that loads the script twice, used
    // to render two forms in the same box.
    if (el.getAttribute("data-pulse-ready") === "1") return;
    el.setAttribute("data-pulse-ready", "1");

    var name = el.getAttribute("data-name") || "Newsletter";
    var color = hexColor(el.getAttribute("data-color"));
    var layout = el.getAttribute("data-layout") || "compact";
    var source = el.getAttribute("data-source") || "embed";

    var wrapper = document.createElement("div");
    wrapper.style.cssText =
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;" +
      "max-width:400px;border:1px solid " + color + "33;border-radius:12px;padding:20px;" +
      "background:#fff;";

    var title = document.createElement("p");
    title.textContent = "Subscribe to " + name;
    title.style.cssText = "margin:0 0 8px;font-weight:600;font-size:15px;color:#111;";
    wrapper.appendChild(title);

    if (layout === "full") {
      var desc = document.createElement("p");
      desc.textContent = "Get the latest insights delivered to your inbox.";
      desc.style.cssText = "margin:0 0 12px;font-size:13px;color:#666;";
      wrapper.appendChild(desc);
    }

    var form = document.createElement("form");
    form.style.cssText = "display:flex;gap:8px;";

    var input = document.createElement("input");
    input.type = "email";
    input.placeholder = "you@example.com";
    input.required = true;
    input.autocomplete = "email";
    // A placeholder is not a label: it vanishes on typing and many screen
    // readers do not announce it.
    input.setAttribute("aria-label", "Email address");
    input.style.cssText =
      "flex:1;padding:8px 12px;border:1px solid #ddd;border-radius:8px;" +
      "font-size:14px;outline:none;";

    var btn = document.createElement("button");
    btn.type = "submit";
    btn.textContent = "Subscribe";
    btn.style.cssText =
      "padding:8px 16px;border:none;border-radius:8px;font-size:14px;" +
      "font-weight:500;cursor:pointer;background:" + color + ";color:" + textOn(color) + ";";

    form.appendChild(input);
    form.appendChild(btn);
    wrapper.appendChild(form);

    var msg = document.createElement("p");
    msg.style.cssText = "margin:8px 0 0;font-size:12px;display:none;";
    // Announced when it changes, so a screen-reader user hears that the
    // subscription worked (or did not) instead of silence.
    msg.setAttribute("role", "status");
    msg.setAttribute("aria-live", "polite");
    wrapper.appendChild(msg);

    var powered = document.createElement("p");
    powered.style.cssText = "margin:10px 0 0;font-size:11px;color:#999;text-align:center;";
    var poweredLink = document.createElement("a");
    poweredLink.href = "https://pulse.doaide.com?ref=embed";
    poweredLink.target = "_blank";
    poweredLink.rel = "noopener";
    poweredLink.textContent = "DoAide Pulse";
    poweredLink.style.cssText = "color:" + color + ";text-decoration:none;font-weight:500;";
    powered.appendChild(document.createTextNode("Powered by "));
    powered.appendChild(poweredLink);
    wrapper.appendChild(powered);

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var email = input.value.trim();
      if (!email) return;
      btn.disabled = true;
      btn.textContent = "…";

      fetch(API_BASE + "/subscribers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email, source: source }),
      })
        .then(function (r) {
          if (r.ok || r.status === 429) {
            msg.textContent = r.ok
              ? "You’re subscribed! \u{1F389}"
              : "Too many requests. Please try again later.";
            msg.style.color = r.ok ? "#16a34a" : "#dc2626";
            msg.style.display = "block";
            if (r.ok) {
              input.value = "";
              form.style.display = "none";
            } else {
              input.focus();
            }
          } else {
            throw new Error("Request failed");
          }
        })
        .catch(function () {
          msg.textContent = "Something went wrong. Please try again.";
          msg.style.color = "#dc2626";
          msg.style.display = "block";
          input.focus();
        })
        .finally(function () {
          btn.disabled = false;
          btn.textContent = "Subscribe";
        });
    });

    el.appendChild(wrapper);
  }

  function mountAll() {
    var containers = document.querySelectorAll("[data-pulse-signup]");
    for (var i = 0; i < containers.length; i++) mount(containers[i]);
  }

  // The snippet loads the script `async`, which can run before the parser has
  // reached a container placed below it — that container got no form at all.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }

  window.__pulseEmbed = { hexColor: hexColor, textOn: textOn, mountAll: mountAll };
})();
