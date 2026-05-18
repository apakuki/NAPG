"""Redaction helpers for log boundaries.

Single source of truth for stripping known-sensitive fields before anything
reaches stdout, files, or the audit DB. Per Phase 1 cross-cutting security:
the goal is to make leaks structurally impossible, not to remember to redact
at every call site.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

REDACTED = "<redacted>"


def redact_url(url: str) -> str:
    """Return scheme://host with any path, query, or userinfo replaced.

    Treats the path and query as secret material — Alchemy, Infura, and most
    managed RPCs embed the API key in the URL path or as a query string, so
    only the scheme and host are safe to log.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    path = f"/{REDACTED}" if parts.path not in ("", "/") or parts.query else ""
    return urlunsplit((parts.scheme, host, path, "", ""))
