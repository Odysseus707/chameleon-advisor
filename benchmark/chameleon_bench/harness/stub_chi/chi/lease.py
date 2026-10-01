"""Lease / reservation side of the bare-metal stub.

Covers both generations (D01): the current Lease object and the legacy
create_lease / add_node_reservation(reservations, ...) list-mutating form. A
gold written either way must execute, or execution would be grading style.
"""
from datetime import timedelta

from . import _state

_LEASES = {}
_SEQ = {"n": 0}


def _hours(duration=None, end_date=None, start_date=None):
    if isinstance(duration, timedelta):
        return round(duration.total_seconds() / 3600, 4)
    return None


class _Reservation(dict):
    """Behaves as both a dict (legacy: res["id"]) and an object (res.id)."""

    @property
    def id(self):
        return self["id"]


class Lease:
    def __init__(self, name=None, duration=None, start_date=None,
                 end_date=None, node_reservations=None,
                 flavor_reservations=None, **kw):
        _SEQ["n"] += 1
        self.name = name
        self.id = f"lease-{_SEQ['n']}"
        self.node_reservations = []
        self.flavor_reservations = []
        self.fip_reservations = []
        self._submitted = False
        self._deleted = False
        self._rec = {
            "name": name, "id": self.id,
            "hours": _hours(duration, end_date, start_date),
            "node_reservations": self.node_reservations,
            "flavor_reservations": self.flavor_reservations,
            "fip_reservations": self.fip_reservations,
            "submitted": False, "deleted": False,
            "site": _state.TRACE["site"],
        }
        _state.TRACE["leases"].append(self._rec)
        _LEASES[self.id] = self
        for r in node_reservations or []:
            self.add_node_reservation(**r)
        for r in flavor_reservations or []:
            self.add_flavor_reservation(**r)

    # -- reservations
    def add_node_reservation(self, amount=1, count=None, node_type=None,
                             resource_properties=None, **kw):
        n = count if count is not None else amount
        if node_type is None and resource_properties:
            node_type = _node_type_from_properties(resource_properties)
        if node_type is None:
            raise RuntimeError(
                "add_node_reservation with no node_type: the request does not "
                "say what hardware it wants.")
        _state.check_node_type(node_type)
        r = _Reservation(id=f"{self.id}-nr{len(self.node_reservations)}",
                         node_type=node_type, amount=n)
        self.node_reservations.append(r)
        return r

    def add_flavor_reservation(self, id=None, amount=1, count=None,
                               flavor=None, **kw):
        n = count if count is not None else amount
        name = id if isinstance(id, str) else (flavor or "unknown")
        r = _Reservation(id=f"{self.id}-fr{len(self.flavor_reservations)}",
                         flavor=name, amount=n)
        self.flavor_reservations.append(r)
        return r

    def add_fip_reservation(self, amount=1, count=None, **kw):
        n = count if count is not None else amount
        # Reserved FIPs get concrete addresses, and they are RECORDED, because
        # the whole point of the reservation is that it is a specific address
        # and not "one of the project's". See associate_floating_ip in
        # server.py for what that distinction costs when it is ignored.
        addrs = [f"192.0.2.{len(_state.RESERVED_FIPS) + i + 1}" for i in range(n)]
        _state.RESERVED_FIPS.update(addrs)
        self.fip_reservations.append({"amount": n, "addresses": addrs})
        return self.fip_reservations[-1]

    def get_reserved_floating_ips(self):
        """The addresses THIS lease reserved, as python-chi returns them.

        python-chi finds them by tag: a floating IP carries
        `reservation:<id>` for the fip_reservation that holds it. So this is
        answerable per-lease, which is exactly what makes binding the right
        one possible - and what `get_free_floating_ip()` throws away.
        """
        return [a for r in self.fip_reservations for a in r.get("addresses", [])]

    # -- lifecycle
    def submit(self, idempotent=False, wait_for_active=False, **kw):
        if not (self.node_reservations or self.flavor_reservations):
            raise RuntimeError(
                "submitting a lease with no reservation: it would reserve "
                "nothing and the instance would have nothing to bind to.")
        self._submitted = True
        self._rec["submitted"] = True
        self._rec["idempotent"] = bool(idempotent)
        self._rec["site"] = _state.TRACE["site"]
        return self

    def delete(self):
        self._deleted = True
        self._rec["deleted"] = True

    def get_reserved_flavors(self):
        from types import SimpleNamespace
        return [SimpleNamespace(name=r["flavor"], id=r["id"])
                for r in self.flavor_reservations]

    def refresh(self):
        return self

    def wait_for_active(self, *a, **kw):
        return self


def _node_type_from_properties(props):
    if isinstance(props, (list, tuple)):
        flat = " ".join(str(x) for x in props)
        for tok in flat.replace('"', " ").replace("'", " ").split():
            if tok.startswith(("compute_", "gpu_", "storage_", "fpga")):
                return tok
    return None


# -- legacy imperative surface ---------------------------------------------

def lease_duration(hours=24, days=None):
    h = hours + (days or 0) * 24
    return ("start", "end", h) if False else ("start", f"+{h}h")


def add_node_reservation(reservation_list, node_type=None, count=1, amount=None,
                         **kw):
    n = amount if amount is not None else count
    _state.check_node_type(node_type)
    reservation_list.append({"resource_type": "physical:host",
                             "node_type": node_type, "amount": n})
    return reservation_list


def add_flavor_reservation(reservation_list, id=None, count=1, amount=None, **kw):
    n = amount if amount is not None else count
    reservation_list.append({"resource_type": "flavor:instance",
                             "flavor": id, "amount": n})
    return reservation_list


def add_fip_reservation(reservation_list, count=1, amount=None, **kw):
    n = amount if amount is not None else count
    reservation_list.append({"resource_type": "virtual:floatingip", "amount": n})
    return reservation_list


def create_lease(name, reservations=None, start_date=None, end_date=None,
                 **kw):
    lease = Lease(name=name)
    for r in reservations or []:
        rt = r.get("resource_type", "")
        if "host" in rt:
            lease.add_node_reservation(amount=r.get("amount", 1),
                                       node_type=r.get("node_type"))
        elif "flavor" in rt:
            lease.add_flavor_reservation(id=r.get("flavor"),
                                         amount=r.get("amount", 1))
        elif "floatingip" in rt:
            lease.add_fip_reservation(amount=r.get("amount", 1))
    lease.submit()
    return {"id": lease.id, "name": name,
            "reservations": [dict(r) for r in lease.node_reservations]}


def get_lease(ref):
    if isinstance(ref, str) and ref in _LEASES:
        return _LEASES[ref]
    return next(iter(_LEASES.values())) if _LEASES else None


def get_node_reservation(lease_ref, **kw):
    """BROKEN, exactly as python-chi 1.2.10 is broken. Verified live.

    This used to return the reservation id, i.e. it modelled the deprecated
    idiom as WORKING. Against the real testbed it is not: `_reservation_matching`
    expects a lease dict while `get_lease` now returns a Lease object, so the
    call dies with `AttributeError: 'Lease' object has no attribute 'get'`.
    Confirmed against CHI@TACC on 2026-09-05 and again on 2026-09-07, both on
    python-chi 1.2.10, with the identical error.

    No gold uses this spelling, so nothing here changes what the golds do. It
    matters for what an ANSWER is graded against: a model that copies the idiom
    from the 20 corpus artifacts still using it would have been graded by a stub
    that disagreed with the testbed, and would have passed while shipping code
    that cannot run. CB38 exists precisely to catch that answer.

    Same class of defect as the lease-id trap in server.py:36-42, and fixed the
    same way - the stub's job is to be wrong in the ways the testbed is wrong.
    """
    raise AttributeError("'Lease' object has no attribute 'get'")


def delete_lease(ref, **kw):
    lease = _LEASES.get(ref) if isinstance(ref, str) else ref
    if lease is None and _LEASES:
        lease = next(iter(_LEASES.values()))
    if lease is not None:
        lease.delete()


def wait_for_active(*a, **kw):
    return None
