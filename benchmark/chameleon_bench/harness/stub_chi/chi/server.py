"""Server side of the bare-metal stub, both generations (D01)."""
from . import _state
from .lease import _LEASES

_SEQ = {"n": 0}
_KNOWN_RESERVATION_IDS = set()


def _all_reservation_ids():
    ids = set()
    for l in _LEASES.values():
        ids |= {r["id"] for r in l.node_reservations}
        ids |= {r["id"] for r in l.flavor_reservations}
    return ids


def _lease_ids():
    return set(_LEASES)


def _is_ipynb() -> bool:
    """True only inside a notebook kernel, as python-chi's own helper is.

    A plain subprocess - which is how verify_golds_exec runs every gold - is
    not a notebook, so this is False there and the widget default raises,
    exactly as it does against the real testbed.
    """
    try:
        from IPython import get_ipython
        return get_ipython() is not None and "IPKernelApp" in get_ipython().config
    except Exception:                                     # noqa: BLE001
        return False


class Server:
    # image_name defaults to CC-Ubuntu22.04 in real python-chi 1.2.10
    # (verified by introspection). A stub that required it would fail golds
    # the real library accepts.
    def __init__(self, name=None, image_name="CC-Ubuntu22.04", image=None,
                 flavor_name=None,
                 flavor_id=None, reservation_id=None, network_name=None, **kw):
        _SEQ["n"] += 1
        self.name = name
        self.id = f"server-{_SEQ['n']}"
        self.status = "ACTIVE"
        img = image_name or image
        bound = reservation_id in _all_reservation_ids() if reservation_id else False

        # The documented trap. VERIFIED LIVE 2026-09-05 against CHI@TACC in
        # project CHI-231225: Nova ACCEPTS a lease id here. The server is
        # created, submit() waits, and it reaches ERROR - it does not fail at
        # construction. An earlier version of this stub raised immediately,
        # which was wrong in a way that mattered: it modelled the trap as loud
        # when the whole danger is that it is quiet. A55's traps_illustrated
        # said so all along ("the failure surfaces only when the instance never
        # boots") and the stub disagreed with the corpus it was built from.
        self._lease_id_as_reservation = bool(
            reservation_id and not bound and reservation_id in _lease_ids())

        self._rec = {
            "name": name, "id": self.id, "image": img,
            "flavor": flavor_name or flavor_id,
            "reservation_id": reservation_id,
            "bound_to_reservation": bool(bound),
            "site": _state.TRACE["site"],
            "submitted": False, "deleted": False,
        }
        _state.TRACE["servers"].append(self._rec)

    def submit(self, idempotent=False, wait_for_active=True, show="widget", **kw):
        if not self._rec["image"]:
            raise RuntimeError("server has no image; it cannot boot.")
        self._rec["submitted"] = True
        if self._lease_id_as_reservation:
            # Live behaviour: status goes to ERROR. With wait_for_active=True
            # (python-chi's default) the caller sees the failure here.
            self.status = "ERROR"
            self._rec["status"] = "ERROR"
            raise RuntimeError(
                f"server reached ERROR: reservation_id="
                f"{self._rec['reservation_id']!r} is a LEASE id, not a "
                "reservation id, so the instance was bound to no reserved "
                "node. Use lease.node_reservations[0]['id']. (Verified against "
                "CHI@TACC 2026-09-05: Nova accepts the call and the instance "
                "fails later, which is what makes this trap quiet.)")
        self.status = "ACTIVE"
        self._rec["status"] = "ACTIVE"

        # THE JUPYTER-ONLY DEFAULT, modelled because the testbed has it.
        # python-chi's Server.submit defaults show="widget", and chi/server.py
        # renders a widget only when _is_ipynb(); anywhere else it raises
        # CHIValueError("Invalid show type"). Crucially it raises HERE - after
        # the instance exists and has reached ACTIVE - so a script that takes
        # the default creates a real machine and then dies, leaving it running.
        # Verified against CHI@TACC on 2026-09-07.
        #
        # The stub had ignored `show` entirely, which meant verify_golds_exec
        # ran every gold in a plain subprocess and passed it. The benchmark was
        # therefore blind to a defect in its own reference answers: 31 of them
        # took the default and none could run outside a notebook. A stub that
        # is right where the testbed is wrong hides exactly the failures the
        # golds are supposed to teach.
        if show == "widget" and not _is_ipynb():
            raise RuntimeError(
                "Invalid show type. Use 'text' or 'widget'. Server.submit() "
                "defaults to show='widget', which renders only inside a "
                "notebook; outside one this raises AFTER the instance is "
                "ACTIVE, leaving it running. Pass show='text' (or show=None) "
                "for code that must run anywhere.")
        return self

    def delete(self):
        self._rec["deleted"] = True

    def associate_floating_ip(self, fip=None, *a, **kw):
        """Requires the address the lease reserved. Modelled, not invented.

        python-chi's `associate_floating_ip()` with no argument calls
        `get_free_floating_ip()`, whose docstring is explicit: "the first
        unallocated floating IP available to your PROJECT". It has no idea
        which lease reserved what. In a shared project - CHI-231225 held 17
        leases while this was being measured - that binds an arbitrary IP,
        possibly one another lease reserved, and when the chosen IP cannot be
        assigned the failure surfaces as `ResourceError: None of the ports can
        route to floating ip ...`, which names neither the real cause nor the
        reservation.

        Observed live: CB14 raised it, CB38 raised it on one run and passed on
        another, CB19 passed - two failures in four attempts. The port is NOT
        the problem; a dedicated experiment found ports=1 and addresses
        present at the instant submit() returns, and the association
        succeeding on the first try when nothing else contended.

        So this raises on the argument-free form. The real API only fails
        SOMETIMES, and a stub that failed sometimes would make the gold gate
        non-deterministic - worse than the blindness it replaces. Failing
        always encodes the required SHAPE: name the address you reserved.

        This is the same defect as the lease-id/reservation-id trap that CB06
        and this wing are built around - reserve one thing, bind to another -
        and it was sitting inside seven golds.
        """
        if fip is None:
            raise RuntimeError(
                "associate_floating_ip() with no address binds whatever "
                "floating IP the PROJECT happens to have free, not the one "
                "this lease reserved. Pass the reserved address: "
                "my_lease.get_reserved_floating_ips()[0].")
        if _state.RESERVED_FIPS and fip not in _state.RESERVED_FIPS:
            raise RuntimeError(
                f"floating ip {fip!r} was not reserved by any lease here.")
        self._rec["floating_ip"] = fip
        return fip

    def refresh(self):
        return self

    def wait_for_active(self, *a, **kw):
        return self

    def wait_for_tcp(self, *a, **kw):
        return self

    def execute(self, *a, **kw):
        return type("R", (), {"stdout": "", "stderr": "", "exited": 0})()


def create_server(name, image_name=None, image=None, flavor_name=None,
                  reservation_id=None, **kw):
    s = Server(name=name, image_name=image_name or image,
               flavor_name=flavor_name, reservation_id=reservation_id, **kw)
    s.submit()
    return s


def get_flavor_id(name):
    return name


def get_server(ref, **kw):
    return None


def list_servers(**kw):
    return []


def delete_server(ref, **kw):
    if hasattr(ref, "delete"):
        ref.delete()


def wait_for_active(*a, **kw):
    return None


def associate_floating_ip(*a, **kw):
    return "127.0.0.1"
