from . import _state

version = "1.0"


def use_site(name):
    return _state.set_site(name)


def choose_site(default=None):
    """Interactive in real python-chi. Here it resolves to its default, and
    records that no site was pinned explicitly - which is the difference an
    answer using choose_site() is making, whether or not it meant to."""
    _state.TRACE["notes"].append("site chosen via choose_site (interactive)")
    return _state.set_site(default) if default else None


def choose_project(default=None):
    return default


def choose_project_name(default=None):
    return default
