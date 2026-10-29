/**
 * Where to send someone after signing in, from the path the gate remembered.
 *
 * Only a path inside this app: it starts with one `/` and the next character
 * is not another `/` or a `\` — browsers read both `//host` and `/\host` as
 * "a different site", which is how a return path becomes an open redirect.
 * `/` itself is refused too: it is the sign-in page, and going "back" there
 * would loop. Anything else answers `null`, and the caller picks the default.
 */
export function safeReturnPath(value) {
  if (typeof value !== "string" || value.length > 2000) return null;
  if (!value.startsWith("/") || value === "/") return null;
  if (value[1] === "/" || value[1] === "\\") return null;
  // A control character can be dropped by the URL parser, turning `/\t/host`
  // into `//host` after the check above has passed.
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f]/.test(value)) return null;
  return value;
}
