"""Tiny dependency-free HTTP/JSON helper (stdlib urllib).

Kept dependency-free so the read/probe path runs without installing anything.
The rest of the package may use richer clients; this is only for GET/JSON.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from .config import settings


@dataclass
class HttpResult:
    url: str
    status: int
    ok: bool
    json: Optional[Any] = None
    error: Optional[str] = None


def get_json(url: str, timeout: Optional[float] = None) -> HttpResult:
    """GET a URL and parse JSON, never raising for network/HTTP errors.

    Returns an HttpResult; inspect `.ok` / `.status` / `.error`.
    """
    timeout = timeout if timeout is not None else settings.http_timeout
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "chi-edge-advisor/0.1 (+probe)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.getcode()
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError as exc:
                return HttpResult(url, status, False, None, f"bad json: {exc}")
            return HttpResult(url, status, 200 <= status < 300, parsed, None)
    except urllib.error.HTTPError as exc:
        return HttpResult(url, exc.code, False, None, f"http {exc.code}")
    except urllib.error.URLError as exc:
        return HttpResult(url, 0, False, None, f"urlerror: {exc.reason}")
    except Exception as exc:  # noqa: BLE001 - defensive: probe must never crash
        return HttpResult(url, 0, False, None, f"{type(exc).__name__}: {exc}")
