"""What the application logs, and where it goes.

Nothing configured logging, and under uvicorn that is not the same as "the
defaults apply". Uvicorn installs handlers on its *own* loggers — ``uvicorn``,
``uvicorn.error``, ``uvicorn.access`` — and leaves the root logger alone. Every
``app.*`` logger propagates to that empty root, where Python falls back to
:data:`logging.lastResort`: a bare :class:`~logging.StreamHandler` fixed at
``WARNING`` with no formatter attached.

Two things followed, and both are the kind of thing you only notice when you
need the logs:

* every ``logger.info`` in the tree was dropped. That is the whole operational
  narrative — what each beat sweep dispatched, what was published where, which
  fallback fired, that the pool was disposed on shutdown. The lines were being
  written and thrown away;
* what did survive arrived as the bare message. No timestamp, no level, no
  logger name. ``broker unavailable, publishing inline`` on a line by itself,
  with nothing to say which process wrote it or when.

Journald stamps its own timestamp onto whatever a unit prints, so the second
was survivable. The first was not: the ``WARNING`` floor meant the box logged
only its failures, and a publish that quietly stopped happening looked exactly
like a publish that never had anything to do.

The format is for ``journalctl``, which is how these logs are actually read
(see ``deploy/DEPLOYMENT.md``) — plain text a person can skim, not JSON for a
shipper nobody has installed.
"""
from __future__ import annotations

import logging
import re
import sys
from contextvars import ContextVar
from urllib.parse import urlsplit

from app.config import settings

#: The request being served on this task, for correlating log lines with the
#: ``X-Request-ID`` the caller was handed back. A context variable rather than
#: anything threaded through call signatures: the services that do the logging
#: are the ones with no idea a request exists, which is exactly why they had
#: nothing to log it against. Workers leave it at the default — a Celery task
#: has no request, and ``-`` says so rather than inheriting a stale id.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

#: Level, request id, source, message. The request id sits early because
#: grepping one out of a day of logs is the thing it exists for.
LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"

#: Third parties that log a line per operation at INFO. Raising the app to INFO
#: without these turns one publish into a dozen lines of HTTP plumbing, which
#: is how a log stops being read.
_NOISY = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "urllib3": logging.WARNING,
    # Not the echo flag — that is off — but the pool's own chatter.
    "sqlalchemy.engine": logging.WARNING,
    "sqlalchemy.pool": logging.WARNING,
    "multipart": logging.WARNING,
}

#: Marks the handler as ours, so :func:`configure_logging` can recognise its own
#: work and replace it rather than stacking a second copy of every line.
_HANDLER_NAME = "pulse"


class RequestIDFilter(logging.Filter):
    """Put the current request id on every record.

    A filter rather than a formatter override because the id has to exist on
    records this application never created — uvicorn's, Celery's, a library's.
    A ``%(request_id)s`` in the format string raises for any record without the
    attribute, and a logging call that raises inside a request handler is a
    worse outage than the one you were trying to diagnose.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Stamp *record* with the current request id, and keep it.

        Never drops a record — the return is always ``True``. A record that
        already carries a ``request_id`` keeps it, which is what lets a task
        set its own without this overwriting it.
        """
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


#: URL path segments that are credentials. Holding the inbound-trigger token
#: is enough to fire the trigger; holding the preview token is enough to read
#: the draft. Both arrive in the path, and every path is logged — by uvicorn's
#: access log on every request, and by the slow-request and server-error lines
#: in ``app.main`` — so journald kept a working copy of each.
#: The digest's one-click unsubscribe link carries an HMAC token after the
#: account id; tests/test_every_credential_in_a_path_is_redacted_from_logs.py
#: walks the route table so the next such route cannot be left off this list.
_SECRET_PATH = re.compile(
    r"(/triggers/inbound/|/content/preview/|/digest/unsubscribe/\d+/)[^/?#\s]+"
)


def redact_path(path: str) -> str:
    """*path* with any credential segment replaced by ``[redacted]``."""
    return _SECRET_PATH.sub(r"\1[redacted]", path or "")


def mask_email(address: str | None) -> str:
    """``sumit@example.com`` → ``s***@example.com``: which mailbox, not whose.

    Enough to tell a log reader which domain a send failed for, or to match a
    line to a support request, without turning the log into a mailing list.
    """
    local, at, domain = (address or "").strip().partition("@")
    if not (at and local and domain):
        return "***"
    return f"{local[0]}***@{domain.lower()}"


def url_for_log(url: str | None) -> str:
    """Scheme and host only. For URLs whose path or query may be the secret.

    A Slack or Discord incoming webhook *is* its path —
    ``https://hooks.slack.com/services/T…/B…/XXXX`` — so logging a webhook URL
    in full logs a credential that lets anyone post to that channel.
    """
    parts = urlsplit(url or "")
    if not parts.scheme or not parts.hostname:
        return "[unparseable url]"
    return f"{parts.scheme}://{parts.hostname}/…"


class AccessPathRedactor(logging.Filter):
    """Redact credential segments from uvicorn's access-log lines.

    Uvicorn formats ``'%s - "%s %s HTTP/%s" %d'`` from ``record.args`` —
    client, method, path, HTTP version, status — so the path is rewritten in
    the args rather than in the message, which is only built at format time.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact the path in an access-log record's arguments; never drops the record."""
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], redact_path(args[2]), *args[3:])
        return True


def resolve_level(name: str) -> int:
    """A level name to its number, falling back to INFO.

    ``LOG_LEVEL`` is a free-text environment variable, and a typo in it should
    not stop the process from starting — nor silently mean ``WARNING``, which
    is what ``getattr(logging, name, ...)`` on a misspelling would produce via
    the module's other integer attributes.
    """
    level = logging.getLevelNamesMapping().get(name.strip().upper())
    return level if isinstance(level, int) else logging.INFO


class OneLineFormatter(logging.Formatter):
    """:data:`LOG_FORMAT`, with line breaks in the message written as ``\\n``.

    The journal splits on newlines, so a message that carries one becomes two
    entries, and the second has no timestamp, level or request id of ours —
    it looks like whatever its text says it is. Messages quote things Pulse
    does not control: a publish failure is logged with the platform's own
    error text, and while most adapters flatten what they quote, Hashnode's
    GraphQL ``errors[].message`` reached the log verbatim. A platform (or
    anyone answering in its place) could write
    ``x\\n2026-10-29 03:00:00,000 ERROR [-] app.main: ...`` into Pulse's log.

    Escaped here, where every line passes, rather than at each call site that
    might quote something. Only the message: a traceback is appended after
    :meth:`formatMessage` and keeps its lines, which is the one multi-line
    record that is ours.
    """

    def formatMessage(self, record: logging.LogRecord) -> str:  # noqa: N802 - stdlib name
        """The formatted line, with CR and LF in the message escaped."""
        message = record.message
        record.message = message.replace("\r", "\\r").replace("\n", "\\n")
        try:
            return super().formatMessage(record)
        finally:
            record.message = message


def configure_logging(*, level: str | None = None) -> None:
    """Install Pulse's handler on the root logger. Idempotent.

    Called from :func:`app.main.create_app` and from the Celery ``setup_logging``
    signal, so every entry point that runs application code gets the same
    output: the API under uvicorn, the worker, beat, and ``python -m app.seed``.

    Only Pulse's own handler is replaced. Uvicorn's handlers stay on uvicorn's
    loggers, which is what keeps access logs looking like access logs; pytest's
    capture handlers are attached elsewhere too and are likewise untouched.
    """
    resolved = resolve_level(level or settings.log_level)
    root = logging.getLogger()

    for existing in [h for h in root.handlers if h.name == _HANDLER_NAME]:
        root.removeHandler(existing)

    # stdout, not stderr: these are ordinary operational lines, and a unit whose
    # every log line is stderr makes `systemctl status` look like a fire.
    handler = logging.StreamHandler(sys.stdout)
    handler.name = _HANDLER_NAME
    handler.setFormatter(OneLineFormatter(LOG_FORMAT))
    handler.addFilter(RequestIDFilter())
    root.addHandler(handler)
    root.setLevel(resolved)

    # On the logger, not a handler: uvicorn attaches its own handler to it, and
    # this has to run whichever handler ends up writing the line.
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessPathRedactor) for f in access.filters):
        access.addFilter(AccessPathRedactor())

    # ``LOG_LEVEL=DEBUG`` is nobody's steady state — it is set by somebody
    # chasing a specific thing, and half of what they are chasing is usually in
    # the HTTP layer. So the floors apply at every ordinary level and lift
    # entirely for DEBUG, rather than being blended with it: a floor that still
    # applied would hide exactly the lines the flag was turned on for.
    everything = resolved <= logging.DEBUG
    for name, floor in _NOISY.items():
        logging.getLogger(name).setLevel(resolved if everything else floor)
