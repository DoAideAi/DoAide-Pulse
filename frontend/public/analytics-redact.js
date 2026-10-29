// Strips credentials out of URLs before Umami records them.
//
// Umami's tracker sends every page's URL, query string included, and the URL
// of the page before it as the referrer. Two of Pulse's URLs carry a secret:
// a preview link (/preview/<token>, a bearer credential for an unpublished
// draft) and the password-reset link (?token=…, a credential for the whole
// account). Both were being stored in analytics in full — the very tokens the
// backend keeps only as hashes.
//
// A blocking file loaded before the tracker, not part of the app bundle: a
// reset or preview link is usually the first page of a visit, and Umami sends
// that pageview before the bundle has run. A file rather than inline because
// the SPA's CSP is script-src 'self' (see theme-init.js). Umami resolves the
// hook by name on every send (data-before-send="pulseRedactAnalytics").
//
// window.pulseRedactUrl is the same function, for src/lib/activity.js and its
// tests, so the rule is written once.
(function () {
  // Path segments that follow these are credentials, whatever they look like.
  var SECRET_SEGMENTS = { preview: ":token" };
  // Query parameters that are credentials. Everything else — utm_* above all —
  // is kept, which is why this does not use data-exclude-search.
  var SECRET_PARAMS = /^(token|invite|key|code|secret|password|signature|sig)$/i;

  function redactPath(path) {
    var parts = path.split("/");
    for (var i = 1; i < parts.length; i++) {
      var hidden = SECRET_SEGMENTS[parts[i - 1]];
      if (hidden && parts[i]) parts[i] = hidden;
    }
    return parts.join("/");
  }

  function redactUrl(value) {
    if (typeof value !== "string" || !value) return value;
    var url;
    try {
      url = new URL(value, window.location.origin);
    } catch (e) {
      return value;
    }
    var params = url.searchParams;
    var names = [];
    params.forEach(function (_v, name) {
      if (SECRET_PARAMS.test(name)) names.push(name);
    });
    for (var j = 0; j < names.length; j++) params.set(names[j], "redacted");
    var search = params.toString();
    var rest = redactPath(url.pathname) + (search ? "?" + search : "");
    // Keep the shape Umami sent: a path stays a path, an absolute URL stays absolute.
    var absolute = /^[a-z][a-z0-9+.-]*:/i.test(value);
    var external = url.origin !== window.location.origin;
    // An external referrer's path is somebody else's site; only its query is
    // a concern, and only if it names a credential.
    if (absolute && external) return url.origin + url.pathname + (search ? "?" + search : "");
    return absolute ? url.origin + rest : rest;
  }

  window.pulseRedactUrl = redactUrl;
  window.pulseRedactAnalytics = function (_type, payload) {
    if (payload && typeof payload === "object") {
      if (payload.url) payload.url = redactUrl(payload.url);
      if (payload.referrer) payload.referrer = redactUrl(payload.referrer);
    }
    return payload;
  };
})();
