"""Stub `chi` package for bare-metal execution verification (chameleon wing).

Backed by the real Blazar capture under $CHI_SNAPSHOT_DIR. Records what an
answer actually did to $CHI_TRACE. See _state.py for what counts as an error.
"""
from . import _state, context, hardware, lease, server  # noqa: F401


def use_site(name):
    return _state.set_site(name)


def set(key, value):  # noqa: A001 - mirrors chi.set
    if key in ("project_name", "project_id"):
        _state.TRACE["project"] = value
    return None


def get(key):
    return _state.TRACE.get("project") if key.startswith("project") else None
