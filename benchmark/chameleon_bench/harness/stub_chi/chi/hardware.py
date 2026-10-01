"""Read-side inventory for the bare-metal stub, from the real capture."""
from types import SimpleNamespace

from . import _state


def get_nodes(node_type=None, filter_reserved=False, **kw):
    site = _state.require_site()
    counts = _state._load_site(site)
    out = []
    for t, c in sorted(counts.items()):
        if node_type is not None and t != node_type:
            continue
        for i in range(c["total"]):
            free = i < c["free"]
            if filter_reserved and not free:
                continue
            # Real chi.hardware.Node (1.2.10) exposes `.type` and `.name`;
            # `node_type` is the get_nodes() FILTER kwarg, not a field.
            # Verified by introspection after the live notebook hit
            # AttributeError: 'Node' object has no attribute 'node_type'.
            out.append(SimpleNamespace(type=t, node_type=t, name=f"{t}-{i}",
                                       node_name=f"{t}-{i}", site=site,
                                       free=free, reservable=True))
    return out


def get_node_types(**kw):
    return sorted(_state._load_site(_state.require_site()))
