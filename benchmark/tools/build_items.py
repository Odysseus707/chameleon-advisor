"""
Benchmark v4 item bank generator (single source of truth).

Reads v3 prompts verbatim from tools/v3_prompts.jsonl (P01-P28, decision D11),
merges per-item golds/checkers/tokens defined below, adds new items N01-N18 and
AV01-AV04, and emits items/*.yaml.

Key-token policy (README): key_tokens contain only CHI@Edge-specific load-bearing
tokens. Values supplied by the prompt itself and general world knowledge (e.g.
"ubuntu:22.04") are excluded. `adapted` tokens are values deliberately changed
from the source artifact (T2 design). T4b items may carry concept tokens
(e.g. "microphone") marking knowledge absent from all artifacts.
"""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CC = ["Container", "create_container"]      # container creators
ADR = ["add_device_reservation"]

SSH_IMG = "ghcr.io/chameleoncloud/edge_ssh_image:latest"
CAM_IMG = "ghcr.io/chameleoncloud/edge-picamera-image:latest"
HAT_IMG = "ghcr.io/chameleoncloud/edge_sensehat_image:latest"
OLLAMA_IMG = "docker.io/ollama/ollama:latest"
JUPYTER_IMG = "quay.io/jupyter/minimal-notebook:latest"


def S(check, group, **kw):
    return {"check": check, "group": group, **kw}


NO_BAREMETAL = S("forbidden_calls", "safety",
                 names=["add_node_reservation", "create_server", "Server",
                        "add_flavor_reservation", "get_flavor_id", "create_instance"])
KNOWN_ONLY = S("profiles_known_only", "safety")
LEASE_MADE = S("required_call", "mechanism", any=["Lease", "create_lease"])
LEASE_SUBMITTED = S("required_call", "mechanism", any=["submit", "create_lease"])
DEV_RES = S("required_call", "mechanism", name="add_device_reservation")
CTR = S("container_call", "mechanism")
WIRING = S("reservation_wiring", "mechanism")
NAME_OK = S("name_no_underscore", "safety")
FIP = S("required_call", "mechanism", name="associate_floating_ip")
EXEC = S("required_call", "mechanism", name="execute")
UPLOAD = S("required_call", "mechanism", name="upload")
DOWNLOAD = S("required_call", "mechanism", name="download")


def machine(v="raspberrypi4-64"):
    return S("kwarg", "specifics", call=ADR, arg=["machine_type", "machine_name"], equals=v)


def amount(n):
    return S("kwarg", "specifics", call=ADR, arg=["amount", "count"], equals=n)


def devname(v):
    return S("kwarg", "specifics", call=ADR, arg=["device_name"], equals=v)


def img(*vals):
    return S("kwarg", "specifics", call=CC, arg=["image_ref", "image"], equals_any=list(vals))


def ports_has(p):
    return S("kwarg", "specifics", call=CC, arg=["exposed_ports"], contains=p)


def profiles_has(p):
    return S("kwarg", "specifics", call=CC, arg=["device_profiles"], contains=p)


def profiles_all(ps):
    return S("kwarg", "specifics", call=CC, arg=["device_profiles"], contains_all=ps)


def envkeys(ks):
    return S("kwarg", "specifics", call=CC, arg=["environment"], keys_include=ks)


def cs(s, group="specifics"):
    return S("required_code_string", group, s=s)


def cany(vals, group="specifics"):
    return S("required_code_string", group, any=vals)


def ts(s, group="specifics"):
    return S("required_text_string", group, s=s)


def hours(n):
    return S("lease_hours", "specifics", hours=n)


def avail(dt=None):
    return S("availability_query", "mechanism", **({"device_type": dt} if dt else {}))


RUNTIME_NV = S("kwarg", "specifics", call=CC, arg=["runtime"], equals="nvidia")
CMD_PRESENT = S("kwarg", "mechanism", call=CC, arg=["command"], present=True)


# --------------------------------------------------------------------------
# Overrides for the 28 ported v3 items. Prompts come verbatim from the jsonl.
# --------------------------------------------------------------------------

V3 = {}

V3["P01"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["site_setup"],
    tokens=dict(mechanism=["choose_site", "choose_project"], specifics=["CHI@Edge"]),
    checkers=[S("required_call", "mechanism", any=["choose_site", "use_site"]),
              cs("CHI@Edge"),
              S("required_call", "mechanism", any=["choose_project", "set"])],
    gold='''from chi import context

context.choose_site(default="CHI@Edge")
context.choose_project()
''')

V3["P02"] = dict(
    target=["A3"], fed=dict(blind=[], matched=["A3"]), intent=dict(matched="T2"),
    traps=["bare_metal_api"],
    tokens=dict(mechanism=["add_device_reservation", "Lease"],
                specifics=["raspberrypi4-64"], adapted=["hours=2"]),
    checkers=[NO_BAREMETAL, LEASE_MADE, DEV_RES, machine(), amount(1), hours(2),
              LEASE_SUBMITTED],
    gold='''from chi import lease
from datetime import timedelta

my_lease = lease.Lease("rpi4-2h-lease", duration=timedelta(hours=2))
my_lease.add_device_reservation(amount=1, machine_type="raspberrypi4-64")
my_lease.submit(idempotent=True)
''')

V3["P03"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["reservation_wiring"],
    tokens=dict(mechanism=["add_device_reservation", "device_reservations"],
                specifics=["raspberrypi4-64"]),
    checkers=[NO_BAREMETAL, DEV_RES, machine(),
              cany(["device_reservations", "get_device_reservation"], "mechanism")],
    gold='''from chi import lease
from datetime import timedelta

my_lease = lease.Lease("rpi4-rid-lease", duration=timedelta(hours=3))
my_lease.add_device_reservation(amount=1, machine_type="raspberrypi4-64")
my_lease.submit(idempotent=True)

reservation_id = my_lease.device_reservations[0]["id"]
print(reservation_id)
''')

V3["P04"] = dict(
    target=["A3"], fed=dict(blind=[], matched=["A3"]), intent=dict(matched="T2"),
    traps=["bare_metal_api", "count_handling"],
    tokens=dict(mechanism=["add_device_reservation", "Lease"],
                specifics=["raspberrypi4-64"], adapted=["amount=3"]),
    checkers=[NO_BAREMETAL, LEASE_MADE, DEV_RES, machine(), amount(3), LEASE_SUBMITTED],
    gold='''from chi import lease
from datetime import timedelta

my_lease = lease.Lease("rpi4-x3-lease", duration=timedelta(hours=4))
my_lease.add_device_reservation(amount=3, machine_type="raspberrypi4-64")
my_lease.submit(idempotent=True)
''')

V3["P05"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["wrong_container_api", "k8s_naming"],
    tokens=dict(mechanism=["container.Container", "reservation_id"], specifics=[]),
    checkers=[NO_BAREMETAL, CTR, WIRING, cs("ubuntu"), NAME_OK,
              S("required_call", "mechanism", name="submit")],
    gold='''from chi import container

# my_lease: the active lease from your reservation step
my_container = container.Container(
    "basic-ubuntu-test",
    image_ref="ubuntu:22.04",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
)
my_container.submit()
''')

V3["P06"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["keepalive_command"],
    tokens=dict(mechanism=["command="], specifics=["sleep"]),
    checkers=[CTR, CMD_PRESENT, cs("sleep")],
    gold='''from chi import container

my_container = container.Container(
    "keepalive-fix",
    image_ref="ubuntu:22.04",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
)
my_container.submit()
''')

V3["P07"] = dict(
    target=["A1"], fed=dict(blind=[], matched=["A1"]), intent=dict(matched="T2"),
    traps=["port_exposure", "floating_ip"],
    tokens=dict(mechanism=["exposed_ports", "associate_floating_ip"], specifics=[],
                adapted=["8080"]),
    checkers=[cs("exposed_ports", "mechanism"), cs("8080"), FIP],
    gold='''from chi import container

my_container = container.Container(
    "web-svc",
    image_ref="ubuntu:22.04",
    exposed_ports=[8080],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
)
my_container.submit()
ip = my_container.associate_floating_ip()
print(ip)
''')

V3["P08"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["exec_api", "return_shape"],
    tokens=dict(mechanism=["execute"], specifics=[]),
    checkers=[EXEC, cs("ls /app"),
              cany([", code", "['output']", '["output"]'], "mechanism")],
    gold='''result, code = my_container.execute("ls /app")
print(result)
''')

V3["P09"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["file_transfer_api"],
    tokens=dict(mechanism=["upload", "download"], specifics=[]),
    checkers=[UPLOAD, DOWNLOAD, cs("model.pt"), cs("results.csv")],
    gold='''my_container.upload("model.pt", "/app/")
my_container.download("/app/results.csv", ".")
''')

V3["P10"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["teardown"],
    tokens=dict(mechanism=["delete"], specifics=[]),
    checkers=[S("teardown", "mechanism", container=True, lease=True)],
    gold='''my_container.delete()
my_lease.delete()
''')

V3["P11"] = dict(
    target=["A1"], fed=dict(blind=[], matched=["A1"], heldout=["A2", "A3"]),
    intent=dict(matched="T1", heldout="T4"),
    traps=["magic_image", "port_exposure", "floating_ip"],
    tokens=dict(mechanism=["reservation_id", "exposed_ports", "associate_floating_ip"],
                specifics=["ghcr.io/chameleoncloud/edge_ssh_image", "22"]),
    checkers=[CTR, WIRING, img(SSH_IMG), ports_has(22), FIP,
              cany(["ssh root@", "root@"]), NAME_OK],
    gold=f'''from chi import container

my_container = container.Container(
    "edge-ssh-box",
    image_ref="{SSH_IMG}",
    exposed_ports=[22],
    reservation_id=my_lease.device_reservations[0]["id"],
)
my_container.submit()
ip = my_container.associate_floating_ip()
print(f"ssh root@{{ip}}")
''')

V3["P12"] = dict(
    target=["A1"], fed=dict(blind=[], matched=["A1"]), intent=dict(matched="T1"),
    traps=["key_injection"],
    tokens=dict(mechanism=["upload", "execute"],
                specifics=["authorized_keys", "/root/.ssh"]),
    checkers=[UPLOAD, EXEC, cs("authorized_keys"), cs("chmod 600"), cs("/root/.ssh")],
    gold="""my_container.upload("./edge_user_public_key", "/root/.ssh/")
my_container.execute('/bin/bash -c "chmod 600 /root/.ssh/authorized_keys"')
my_container.execute('/bin/bash -c "cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys"')
""")

V3["P13"] = dict(
    target=["A1"], fed=dict(blind=[], matched=["A1"], heldout=["A2", "A3"]),
    intent=dict(matched="T1", heldout="T4"),
    traps=["magic_image"],
    tokens=dict(mechanism=[], specifics=["ghcr.io/chameleoncloud/edge_ssh_image", "22"]),
    checkers=[ts("ghcr.io/chameleoncloud/edge_ssh_image"), ts("22")],
    gold=f'''# Image: {SSH_IMG}
# Exposed port: 22  ->  exposed_ports=[22]
''')

V3["P14"] = dict(
    target=["A1"], fed=dict(blind=[], matched=["A1"]), intent=dict(matched="T1"),
    traps=["bare_metal_api", "magic_image", "key_injection", "floating_ip"],
    tokens=dict(mechanism=["add_device_reservation", "reservation_id",
                           "associate_floating_ip", "upload"],
                specifics=["ghcr.io/chameleoncloud/edge_ssh_image", "raspberrypi4-64",
                           "authorized_keys"]),
    checkers=[NO_BAREMETAL, DEV_RES, machine(), CTR, WIRING, img(SSH_IMG),
              ports_has(22), UPLOAD, cs("authorized_keys"), FIP, NAME_OK],
    gold=f'''from chi import context, lease, container
from datetime import timedelta

context.choose_site(default="CHI@Edge")
context.choose_project()

my_lease = lease.Lease("vscode-pi-lease", duration=timedelta(hours=4))
my_lease.add_device_reservation(amount=1, machine_type="raspberrypi4-64")
my_lease.submit(idempotent=True)

my_container = container.Container(
    "vscode-ssh-target",
    image_ref="{SSH_IMG}",
    exposed_ports=[22],
    reservation_id=my_lease.device_reservations[0]["id"],
)
my_container.submit()

my_container.upload("./edge_user_public_key", "/root/.ssh/")
my_container.execute('/bin/bash -c "chmod 600 /root/.ssh/authorized_keys"')
my_container.execute('/bin/bash -c "cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys"')

ip = my_container.associate_floating_ip()
print(f"Point VS Code Remote-SSH at root@{{ip}}")
''')

V3["P15"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["live_state", "peripheral_discovery"],
    tokens=dict(mechanism=["get_devices", "filter_reserved", "add_device_reservation"],
                specifics=["iot-rpi4-picam", "raspberrypi4-64"]),
    checkers=[avail("raspberrypi4-64"), cs("iot-rpi4-picam"), DEV_RES, NO_BAREMETAL],
    gold='''from chi import hardware, lease
from datetime import timedelta

devs = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
picam_devs = [d for d in devs if d.device_name.startswith("iot-rpi4-picam")]

my_lease = lease.Lease("picam-lease", duration=timedelta(hours=3))
my_lease.add_device_reservation(devices=[picam_devs[0]])
my_lease.submit(idempotent=True)
''')

V3["P16"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"], heldout=["A1", "A3"]),
    intent=dict(matched="T1", heldout="T4"),
    traps=["magic_profile", "magic_image", "keepalive_command"],
    tokens=dict(mechanism=["device_profiles", "reservation_id"],
                specifics=["pi_libcamera", "ghcr.io/chameleoncloud/edge-picamera-image"]),
    checkers=[CTR, WIRING, profiles_has("pi_libcamera"), img(CAM_IMG), CMD_PRESENT,
              cs("sleep"), KNOWN_ONLY, NAME_OK],
    gold=f'''from chi import container

my_container = container.Container(
    "picam-run-01",
    image_ref="{CAM_IMG}",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)
my_container.submit()
''')

V3["P17"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"], heldout=["A1", "A3"]),
    intent=dict(matched="T1", heldout="T4"),
    traps=["magic_command"],
    tokens=dict(mechanism=["execute", "download"],
                specifics=["rpicam-still", "--width 1920"]),
    checkers=[EXEC, cs("rpicam-still"), cs("--width 1920"), cs("--height 1080"),
              DOWNLOAD],
    gold='''result, code = my_container.execute(
    "rpicam-still --nopreview --output /app/still.png --width 1920 --height 1080"
)
my_container.download("/app/still.png", ".")
''')

V3["P18"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["magic_command"],
    tokens=dict(mechanism=["execute"], specifics=["rpicam-vid", "-t 5000"]),
    checkers=[EXEC, cs("rpicam-vid"), cs("-t 5000"), cs("--framerate")],
    gold='''result, code = my_container.execute(
    "rpicam-vid --nopreview -t 5000 --output /app/video1.mp4 --width 1920 --height 1080 --framerate 24"
)
''')

V3["P19"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["magic_command"],
    tokens=dict(mechanism=["execute"], specifics=["rpicam-hello", "--list-cameras"]),
    checkers=[EXEC, cs("rpicam-hello"), cs("--list-cameras")],
    gold='''result, code = my_container.execute("rpicam-hello --nopreview --list-cameras")
print(result)
''')

V3["P20"] = dict(
    target=["A3"], fed=dict(blind=[], matched=["A3"]), intent=dict(matched="T1"),
    traps=["device_pinning"],
    tokens=dict(mechanism=["add_device_reservation", "device_name"],
                specifics=["iot-rpi4-picam3", "raspberrypi4-64"]),
    checkers=[NO_BAREMETAL, DEV_RES, machine(), amount(1), devname("iot-rpi4-picam3")],
    gold='''from chi import lease
from datetime import timedelta

my_lease = lease.Lease("sensehat-lease", duration=timedelta(hours=4))
my_lease.add_device_reservation(
    amount=1, machine_type="raspberrypi4-64", device_name="iot-rpi4-picam3"
)
my_lease.submit(idempotent=True)
''')

V3["P21"] = dict(
    target=["A3"], fed=dict(blind=[], matched=["A3"], heldout=["A1", "A2"]),
    intent=dict(matched="T1", heldout="T4"),
    traps=["magic_profile", "magic_image"],
    tokens=dict(mechanism=["device_profiles", "reservation_id"],
                specifics=["pi_sensehat", "ghcr.io/chameleoncloud/edge_sensehat_image"]),
    checkers=[CTR, WIRING, profiles_has("pi_sensehat"), img(HAT_IMG), CMD_PRESENT,
              cs("sleep"), KNOWN_ONLY, NAME_OK],
    gold=f'''from chi import container

my_container = container.Container(
    name="edge-rpi-sensehat",
    image_ref="{HAT_IMG}",
    device_profiles=["pi_sensehat"],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["-c", "sleep infinity"],
)
my_container.submit()
''')

V3["P22"] = dict(
    target=["A3"], fed=dict(blind=[], matched=["A3"], heldout=["A1", "A2"]),
    intent=dict(matched="T1", heldout="T4"),
    traps=["peripheral_library"],
    tokens=dict(mechanism=["execute"], specifics=["sense_hat", "get_humidity"]),
    checkers=[EXEC, cany(["sense_hat", "SenseHat"]),
              cany(["get_humidity", "get_pressure", "get_temperature"])],
    gold='''cmd_str = """
from sense_hat import SenseHat
sense = SenseHat()
print(sense.get_pressure(), sense.get_humidity(), sense.get_temperature_from_humidity())
"""
stdout, code = my_container.execute(f"python3 -c '{cmd_str}'")
print(stdout)
''')

V3["P23"] = dict(
    target=["A3"], fed=dict(blind=[], matched=["A3"]), intent=dict(matched="T1"),
    traps=["magic_command"],
    tokens=dict(mechanism=["execute"], specifics=["i2cdetect -y 1"]),
    checkers=[EXEC, cs("i2cdetect -y 1")],
    gold='''result, code = my_container.execute("i2cdetect -y 1")
print(result)
''')

V3["P24"] = dict(
    target=["A3"], fed=dict(blind=[], matched=["A3"], heldout=["A1", "A2"]),
    intent=dict(matched="T1", heldout="T4"),
    traps=["magic_profile", "magic_image"],
    tokens=dict(mechanism=[],
                specifics=["pi_sensehat", "ghcr.io/chameleoncloud/edge_sensehat_image"]),
    checkers=[ts("pi_sensehat"), ts("ghcr.io/chameleoncloud/edge_sensehat_image")],
    gold=f'''# Device profile: device_profiles=["pi_sensehat"]  (Waveshare HAT (B): "pi_gpio")
# Image: {HAT_IMG}
''')

V3["P25"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["live_state"],
    tokens=dict(mechanism=["get_devices", "filter_reserved"], specifics=[]),
    checkers=[avail(), cany(["device_type", "device_name"], "mechanism")],
    gold='''from chi import hardware

devs = hardware.get_devices(filter_reserved=True)
for d in devs:
    print(d.device_name, d.device_type)
''')

V3["P26"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["live_state"],
    tokens=dict(mechanism=["get_devices", "filter_reserved"],
                specifics=["raspberrypi4-64"]),
    checkers=[avail("raspberrypi4-64"), cany(["device_name"], "mechanism")],
    gold='''from chi import hardware

devs = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
free_names = [d.device_name for d in devs]
target = "iot-rpi4-01"
print(f"{target} is free right now" if target in free_names else f"{target} is not free")
''')

V3["P27"] = dict(
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T4"),
    traps=["live_state", "magic_profile"],
    tokens=dict(mechanism=["get_devices"], specifics=["supported_device_profiles"]),
    checkers=[S("required_call", "mechanism", name="get_devices"),
              cs("supported_device_profiles")],
    gold='''from chi import hardware

# Device objects expose supported_device_profiles (verified against python-chi);
# this is not documented in the tutorial artifacts, which hardcode profile names.
devs = hardware.get_devices(filter_reserved=True)
for d in devs:
    print(d.device_name, d.supported_device_profiles)
''',
    notes="Gold upgraded from v3 (which pointed at README prose) to the verified "
          "supported_device_profiles field from the advisor prototype probe. "
          "Computed tier vs matched fed set is honestly T4: no artifact documents "
          "this field. Logged as D15.")

V3["P28"] = dict(
    target=["A1"], fed=dict(blind=[], matched=["A1"]), intent=dict(matched="T1"),
    traps=["bare_metal_api", "wrong_container_api"],
    tokens=dict(mechanism=["add_device_reservation", "reservation_id"],
                specifics=["raspberrypi4-64"]),
    checkers=[NO_BAREMETAL, DEV_RES,
              S("kwarg", "specifics", call=ADR, arg=["machine_type", "machine_name"],
                present=True),
              CTR, WIRING],
    gold='''from chi import context, lease, container
from datetime import timedelta

context.choose_site(default="CHI@Edge")
context.choose_project()

my_lease = lease.Lease("converted-edge-lease", duration=timedelta(hours=4))
my_lease.add_device_reservation(amount=1, machine_type="raspberrypi4-64")
my_lease.submit(idempotent=True)

my_container = container.Container(
    "converted-edge-run",
    image_ref="ubuntu:22.04",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
)
my_container.submit()
''')


# --------------------------------------------------------------------------
# New items
# --------------------------------------------------------------------------

NEW = []

NEW.append(dict(
    id="N01", category="Multi-device", axis="ACT", lineage="new",
    prompt="Reserve three raspberrypi4-64 devices on CHI@Edge for 6 hours in one "
           "lease, and launch an SSH-enabled container on the lease so I can log "
           "in as root.",
    trap="Adapted count and duration; bare-metal substitution; SSH image.",
    target=["A1"], fed=dict(blind=[], matched=["A1"]), intent=dict(matched="T2"),
    traps=["bare_metal_api", "magic_image"],
    tokens=dict(mechanism=["add_device_reservation", "reservation_id",
                           "associate_floating_ip"],
                specifics=["ghcr.io/chameleoncloud/edge_ssh_image"],
                adapted=["hours=6", "amount=3"]),
    checkers=[NO_BAREMETAL, DEV_RES, machine(), amount(3), hours(6), CTR, WIRING,
              img(SSH_IMG), ports_has(22), FIP, NAME_OK],
    gold=f'''from chi import lease, container
from datetime import timedelta

my_lease = lease.Lease("three-pi-ssh-lease", duration=timedelta(hours=6))
my_lease.add_device_reservation(amount=3, machine_type="raspberrypi4-64")
my_lease.submit(idempotent=True)

my_container = container.Container(
    "three-pi-ssh-box",
    image_ref="{SSH_IMG}",
    exposed_ports=[22],
    reservation_id=my_lease.device_reservations[0]["id"],
)
my_container.submit()
ip = my_container.associate_floating_ip()
print(f"ssh root@{{ip}}")
'''))

NEW.append(dict(
    id="N02", category="Peripherals · Camera", axis="ACT", lineage="new",
    prompt="Record a 10-second 720p video at 30 fps from the Pi camera and "
           "download it to my machine.",
    trap="All three rpicam-vid parameters adapted from the tutorial values.",
    target=["A2"], fed=dict(blind=[], matched=["A2"], heldout=["A1", "A3", "A6"]),
    intent=dict(matched="T2", heldout="T4"),
    traps=["magic_command"],
    tokens=dict(mechanism=["execute", "download"], specifics=["rpicam-vid"],
                adapted=["-t 10000", "--width 1280", "--framerate 30"]),
    checkers=[EXEC, cs("rpicam-vid"), cs("-t 10000"), cs("--width 1280"),
              cs("--framerate 30"), DOWNLOAD],
    gold='''result, code = my_container.execute(
    "rpicam-vid --nopreview -t 10000 --output /app/clip.mp4 --width 1280 --height 720 --framerate 30"
)
my_container.download("/app/clip.mp4", ".")
'''))

NEW.append(dict(
    id="N03", category="Peripherals · Camera", axis="ACT", lineage="new",
    prompt="Give me a 12-hour lease on a camera-equipped Pi and capture a 640x480 "
           "still from it.",
    trap="Duration and resolution adapted; peripheral discovery still required.",
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T2"),
    traps=["magic_profile", "live_state", "magic_command"],
    tokens=dict(mechanism=["get_devices", "device_profiles"],
                specifics=["pi_libcamera", "iot-rpi4-picam"],
                adapted=["hours=12", "--width 640"]),
    checkers=[avail("raspberrypi4-64"), cs("iot-rpi4-picam"), hours(12),
              profiles_has("pi_libcamera"), img(CAM_IMG), cs("rpicam-still"),
              cs("--width 640"), cs("--height 480"), DOWNLOAD, KNOWN_ONLY, WIRING],
    gold=f'''from chi import hardware, lease, container
from datetime import timedelta

devs = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
picam_devs = [d for d in devs if d.device_name.startswith("iot-rpi4-picam")]

my_lease = lease.Lease("picam-12h-lease", duration=timedelta(hours=12))
my_lease.add_device_reservation(devices=[picam_devs[0]])
my_lease.submit(idempotent=True)

my_container = container.Container(
    "picam-12h-run",
    image_ref="{CAM_IMG}",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)
my_container.submit()

result, code = my_container.execute(
    "rpicam-still --nopreview --output /app/small.png --width 640 --height 480"
)
my_container.download("/app/small.png", ".")
'''))

NEW.append(dict(
    id="N04", category="Peripherals · GPIO", axis="VALIDATE", lineage="new",
    prompt="The Waveshare Sense HAT (B) is attached to iot-rpi-cm4-02. Reserve "
           "that device and launch the sensor container configured so the GPIO "
           "libraries work despite the missing devicetree info inside containers; "
           "then list what's on the I2C bus.",
    trap="Choosing pi_sensehat because 'Sense HAT' is in the name (the Waveshare "
         "variant needs pi_gpio + three env-var workarounds).",
    target=["A3"], fed=dict(blind=[], matched=["A3"], heldout=["A1", "A2"]),
    intent=dict(matched="T1", heldout="T4"),
    traps=["magic_profile", "env_workaround"],
    tokens=dict(mechanism=["device_profiles", "environment"],
                specifics=["pi_gpio", "iot-rpi-cm4-02", "RPI_LGPIO_REVISION"]),
    checkers=[DEV_RES, devname("iot-rpi-cm4-02"), CTR, WIRING,
              profiles_has("pi_gpio"), img(HAT_IMG),
              envkeys(["RPI_LGPIO_REVISION", "BLINKA_FORCECHIP", "BLINKA_FORCEBOARD"]),
              cs("i2cdetect"), KNOWN_ONLY, NAME_OK],
    gold=f'''from chi import lease, container
from datetime import timedelta

my_lease = lease.Lease("waveshare-lease", duration=timedelta(hours=4))
my_lease.add_device_reservation(
    amount=1, machine_type="raspberrypi4-64", device_name="iot-rpi-cm4-02"
)
my_lease.submit(idempotent=True)

environment_vars = {{
    "RPI_LGPIO_REVISION": "0xd03140",
    "BLINKA_FORCECHIP": "BCM2XXX",
    "BLINKA_FORCEBOARD": "RASPBERRY_PI_CM4",
}}

my_container = container.Container(
    name="edge-waveshare-sensehat",
    image_ref="{HAT_IMG}",
    device_profiles=["pi_gpio"],
    environment=environment_vars,
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["-c", "sleep infinity"],
)
my_container.submit()

result, code = my_container.execute("i2cdetect -y 1")
print(result)
'''))

NEW.append(dict(
    id="N05", category="GPU / LLM", axis="ACT", lineage="new",
    prompt="I already have an active CHI@Edge lease named 'my-llm-lease' on a "
           "GPU-capable device. Launch an Ollama container on it with GPU support, "
           "exposing only the Ollama API port, and give it a public IP.",
    trap="Missing runtime='nvidia'; wrong port; re-creating the lease.",
    target=["A4"], fed=dict(blind=[], matched=["A4"], heldout=["A1", "A2", "A3"]),
    intent=dict(matched="T2", heldout="T4"),
    traps=["gpu_runtime", "existing_lease"],
    tokens=dict(mechanism=["get_lease", "reservation_id", "associate_floating_ip"],
                specifics=["runtime=\"nvidia\"", "docker.io/ollama/ollama", "11434"],
                adapted=["exposed_ports=[11434]"]),
    checkers=[S("required_call", "mechanism", name="get_lease"), CTR, WIRING,
              RUNTIME_NV, img(OLLAMA_IMG), ports_has(11434), FIP, NAME_OK,
              NO_BAREMETAL],
    gold=f'''from chi import container, context, lease

context.version = "1.0"
context.choose_project()
context.choose_site(default="CHI@Edge")

l = lease.get_lease("my-llm-lease")

c = container.Container(
    name="ollama-edge-serve",
    reservation_id=l.device_reservations[0]["id"],
    image_ref="{OLLAMA_IMG}",
    runtime="nvidia",
    exposed_ports=[11434],
)
c.submit(idempotent=True)
c.associate_floating_ip()
'''))

NEW.append(dict(
    id="N06", category="API translation", axis="VALIDATE", lineage="new",
    prompt='''Our old tutorial script below uses the deprecated imperative python-chi style. Rewrite it using the current object-oriented API (lease.Lease / container.Container), keeping the behavior identical.

```python
import chi
from chi import lease, container
chi.use_site("CHI@Edge")
chi.set("project_name", "CHI-000000")
res = []
lease.add_device_reservation(res, machine_name="raspberrypi4-64", count=1)
start_date, end_date = lease.lease_duration(days=0, hours=10)
l = lease.create_lease("demo-lease", res, start_date=start_date, end_date=end_date)
lease.wait_for_active(l["id"])
my_container = container.create_container(
    "demo-app", image="python:3.9-slim",
    reservation_id=lease.get_device_reservation(l["id"]),
    exposed_ports=[22], platform_version=2,
)
```''',
    trap="Keeping create_lease/create_container; losing the 10-hour duration or "
         "reservation wiring in translation.",
    target=["A2"], fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
    traps=["api_generation", "reservation_wiring"],
    tokens=dict(mechanism=["lease.Lease", "container.Container",
                           "device_reservations"], specifics=[]),
    checkers=[S("required_call", "mechanism", name="Lease"),
              S("required_call", "mechanism", name="Container"),
              S("forbidden_calls", "specifics",
                names=["create_lease", "create_container"]),
              hours(10),
              machine(), amount(1), ports_has(22), WIRING, NO_BAREMETAL,
              S("required_call", "mechanism", name="submit")],
    gold='''from chi import lease, container
from datetime import timedelta

my_lease = lease.Lease("demo-lease", duration=timedelta(hours=10))
my_lease.add_device_reservation(amount=1, machine_type="raspberrypi4-64")
my_lease.submit(idempotent=True)

my_container = container.Container(
    "demo-app",
    image_ref="python:3.9-slim",
    exposed_ports=[22],
    reservation_id=my_lease.device_reservations[0]["id"],
)
my_container.submit()
'''))

NEW.append(dict(
    id="N07", category="Multi-device", axis="ACT", lineage="new",
    prompt="Reserve two Raspberry Pi 4s in one CHI@Edge lease and start an "
           "SSH-enabled container on each of them.",
    trap="One reservation but only one container; separate leases per device.",
    target=["A1"], fed=dict(blind=[], matched=["A1"]), intent=dict(matched="T1"),
    traps=["bare_metal_api", "multi_container"],
    tokens=dict(mechanism=["add_device_reservation", "reservation_id"],
                specifics=["ghcr.io/chameleoncloud/edge_ssh_image"]),
    checkers=[NO_BAREMETAL, DEV_RES, machine(), amount(2), CTR, WIRING,
              img(SSH_IMG), ports_has(22), NAME_OK],
    gold=f'''from chi import lease, container
from datetime import timedelta

my_lease = lease.Lease("two-ssh-lease", duration=timedelta(hours=4))
my_lease.add_device_reservation(amount=2, machine_type="raspberrypi4-64")
my_lease.submit(idempotent=True)

reservation_id = my_lease.device_reservations[0]["id"]
containers = []
for i in range(2):
    c = container.Container(
        f"ssh-box-{{i}}",
        image_ref="{SSH_IMG}",
        exposed_ports=[22],
        reservation_id=reservation_id,
    )
    c.submit()
    containers.append(c)
''',
    notes="The per-device fan-out (one container per reserved device) is graded on "
          "the human axis; checkers verify amount=2 plus a correct container path."))

NEW.append(dict(
    id="N08", category="Existing lease", axis="ACT", lineage="new",
    prompt="My lease 'serve-edge-vr' is already active on a Raspberry Pi 5. Launch "
           "the Jupyter minimal-notebook container on it, give it a public IP, and "
           "show me how to find the notebook's token URL from the container logs.",
    trap="Re-creating the lease; missing get_logs; wrong image/port.",
    target=["A5"], fed=dict(blind=[], matched=["A5"], heldout=["A1", "A2", "A3"]),
    intent=dict(matched="T1", heldout="T4"),
    traps=["existing_lease", "magic_image"],
    tokens=dict(mechanism=["get_lease", "reservation_id", "get_logs"],
                specifics=["quay.io/jupyter/minimal-notebook", "8888"]),
    checkers=[S("required_call", "mechanism", name="get_lease"), CTR, WIRING,
              img(JUPYTER_IMG), ports_has(8888), FIP,
              S("required_call", "specifics", name="get_logs"), NAME_OK],
    gold=f'''from chi import container, context, lease
import chi

context.version = "1.0"
context.choose_project()
context.choose_site(default="CHI@Edge")

l = lease.get_lease("serve-edge-vr")

c = container.Container(
    name="node-serve-edge-vr",
    reservation_id=l.device_reservations[0]["id"],
    image_ref="{JUPYTER_IMG}",
    exposed_ports=[8888],
)
c.submit(idempotent=True, wait_timeout=1200)
c.associate_floating_ip()

print(chi.container.get_logs(c.id))
# Look for http://127.0.0.1:8888/lab?token=... and swap in the floating IP.
'''))

NEW.append(dict(
    id="N09", category="Composition", axis="ACT", lineage="new",
    prompt="Reserve a camera-equipped Pi, start the camera container, and retrofit "
           "SSH access into it (port 22, my public key, root login) so a teammate "
           "can log in and run captures themselves.",
    trap="Camera image has no sshd; must be installed at runtime (edge-cpu-inference "
         "pattern) while keeping the pi_libcamera profile.",
    target=["A2", "A6"], fed=dict(blind=[], matched=["A2", "A6"]),
    intent=dict(matched="T3"),
    traps=["composition", "magic_profile", "key_injection"],
    tokens=dict(mechanism=["device_profiles", "associate_floating_ip", "upload"],
                specifics=["pi_libcamera", "openssh-server", "authorized_keys"]),
    checkers=[avail("raspberrypi4-64"), profiles_has("pi_libcamera"), img(CAM_IMG),
              ports_has(22), EXEC, cs("openssh-server"), cs("authorized_keys"),
              cs("chmod 600"), cany(["service ssh start", "/usr/sbin/sshd"]),
              UPLOAD, FIP, WIRING, KNOWN_ONLY, NO_BAREMETAL],
    gold=f'''from chi import hardware, lease, container
from datetime import timedelta

devs = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
picam_devs = [d for d in devs if d.device_name.startswith("iot-rpi4-picam")]

my_lease = lease.Lease("cam-ssh-lease", duration=timedelta(hours=4))
my_lease.add_device_reservation(devices=[picam_devs[0]])
my_lease.submit(idempotent=True)

my_container = container.Container(
    "cam-ssh-run",
    image_ref="{CAM_IMG}",
    exposed_ports=[22],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)
my_container.submit()

my_container.execute("apt update")
my_container.execute("apt -y install openssh-server")
my_container.execute("mkdir -p /root/.ssh")
my_container.upload("./tmp_keys/authorized_keys", "/root/.ssh")
my_container.execute("chmod 700 /root/.ssh")
my_container.execute("chmod 600 /root/.ssh/authorized_keys")
my_container.execute("service ssh start")

ip = my_container.associate_floating_ip()
print(f"ssh root@{{ip}}")
'''))

NEW.append(dict(
    id="N10", category="Composition", axis="ACT", lineage="new",
    prompt="The device iot-rpi4-picam3 has both a camera module and a Sense HAT "
           "attached. Reserve it and launch ONE container that can access both "
           "peripherals; then verify each (list cameras; probe the sensor bus).",
    trap="device_profiles is a list and can carry both profiles; models tend to "
         "pick one profile or launch two containers.",
    target=["A2", "A3"], fed=dict(blind=[], matched=["A2", "A3"]),
    intent=dict(matched="T3"),
    traps=["composition", "magic_profile"],
    tokens=dict(mechanism=["device_profiles"],
                specifics=["pi_libcamera", "pi_sensehat", "iot-rpi4-picam3"]),
    checkers=[DEV_RES, devname("iot-rpi4-picam3"), CTR, WIRING,
              profiles_all(["pi_libcamera", "pi_sensehat"]), KNOWN_ONLY,
              EXEC, cs("rpicam-hello"), cany(["i2cdetect", "sense_hat", "SenseHat"]),
              NAME_OK],
    gold=f'''from chi import lease, container
from datetime import timedelta

my_lease = lease.Lease("dual-periph-lease", duration=timedelta(hours=4))
my_lease.add_device_reservation(
    amount=1, machine_type="raspberrypi4-64", device_name="iot-rpi4-picam3"
)
my_lease.submit(idempotent=True)

my_container = container.Container(
    "dual-periph-run",
    image_ref="{CAM_IMG}",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera", "pi_sensehat"],
)
my_container.submit()

result, code = my_container.execute("rpicam-hello --nopreview --list-cameras")
print(result)
result, code = my_container.execute("i2cdetect -y 1")
print(result)
''',
    notes="Gold uses the camera image; sensor-side python libs may need a runtime "
          "install. The checked core is profile-list composition + per-peripheral "
          "verification commands."))

NEW.append(dict(
    id="N11", category="Composition", axis="ACT", lineage="new",
    prompt="Reserve the Pi 5 named nyu-rpi5-03 for exactly 2 hours using "
           "python-chi (no Horizon GUI), then launch the Jupyter minimal-notebook "
           "container on it with port 8888 and a public IP.",
    trap="The Pi-5 tutorial only shows GUI leasing; the python-chi device_name "
         "lease pattern must come from the camera artifact.",
    target=["A2", "A5"], fed=dict(blind=[], matched=["A2", "A5"]),
    intent=dict(matched="T3"),
    traps=["composition", "device_pinning"],
    tokens=dict(mechanism=["add_device_reservation", "device_name",
                           "reservation_id"],
                specifics=["nyu-rpi5-03", "quay.io/jupyter/minimal-notebook"]),
    checkers=[DEV_RES, devname("nyu-rpi5-03"), hours(2), CTR, WIRING,
              img(JUPYTER_IMG), ports_has(8888), FIP, NO_BAREMETAL, NAME_OK],
    gold=f'''from chi import context, lease, container
from datetime import timedelta

context.version = "1.0"
context.choose_project()
context.choose_site(default="CHI@Edge")

my_lease = lease.Lease("rpi5-jupyter-lease", duration=timedelta(hours=2))
my_lease.add_device_reservation(device_name="nyu-rpi5-03", amount=1)
my_lease.submit(idempotent=True)

c = container.Container(
    name="rpi5-jupyter",
    reservation_id=my_lease.device_reservations[0]["id"],
    image_ref="{JUPYTER_IMG}",
    exposed_ports=[8888],
)
c.submit(idempotent=True)
c.associate_floating_ip()
'''))

NEW.append(dict(
    id="N12", category="Composition", axis="ACT", lineage="new",
    prompt="Capture a photo with the Pi camera, then classify it with the "
           "quantized MobileNet TFLite model inside the same container.",
    trap="Combining the camera stack (profile/image) with the inference tooling "
         "(tflite-runtime, model file) from a different artifact.",
    target=["A2", "A6"], fed=dict(blind=[], matched=["A2", "A6"]),
    intent=dict(matched="T3"),
    traps=["composition", "magic_profile", "magic_command"],
    tokens=dict(mechanism=["device_profiles", "upload", "execute"],
                specifics=["pi_libcamera", "rpicam-still", "tflite-runtime",
                           "mobilenet_v2_1.0_224_quantized_1_default_1.tflite"]),
    checkers=[profiles_has("pi_libcamera"), img(CAM_IMG), cs("rpicam-still"),
              UPLOAD, EXEC, cs("tflite-runtime"),
              cs("mobilenet_v2_1.0_224_quantized_1_default_1.tflite"),
              KNOWN_ONLY, WIRING],
    gold=f'''from chi import container

my_container = container.Container(
    "cam-infer-run",
    image_ref="{CAM_IMG}",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)
my_container.submit()

my_container.execute(
    "rpicam-still --nopreview --output /root/photo.jpg --width 1920 --height 1080"
)
my_container.upload("./image_model", "/root/")
my_container.execute("pip install tflite-runtime Pillow")
result, code = my_container.execute(
    "python /root/image_model/model.py "
    "--model mobilenet_v2_1.0_224_quantized_1_default_1.tflite "
    "--label imagenet_labels.txt --image /root/photo.jpg"
)
print(result)
'''))

NEW.append(dict(
    id="N13", category="API translation", axis="ACT", lineage="new",
    prompt="Our lab standardized on the classic imperative python-chi API. Using "
           "ONLY that style (module functions - no Lease/Container classes), "
           "reserve one Pi 4 for 10 hours starting now and launch python:3.9-slim "
           "on it with SSH installed and reachable from outside.",
    trap="platform_version=2 is mandatory on create_container; OO habits leak in.",
    target=["A6"], fed=dict(blind=[], matched=["A6"], heldout=["A2", "A3"]),
    intent=dict(matched="T1", heldout="T4"),
    traps=["api_generation", "platform_version"],
    tokens=dict(mechanism=["create_lease", "create_container",
                           "get_device_reservation"],
                specifics=["platform_version", "python:3.9-slim", "openssh-server"]),
    checkers=[S("required_call", "mechanism", name="create_lease"),
              S("required_call", "mechanism", name="create_container"),
              S("forbidden_calls", "specifics", names=["Lease", "Container"]),
              S("kwarg", "safety", call=["create_container"],
                arg=["platform_version"], present=True),
              hours(10), machine(), amount(1), ports_has(22),
              cs("openssh-server"), FIP, WIRING, NO_BAREMETAL],
    gold='''import chi, os
from chi import lease, container

chi.use_site("CHI@Edge")
chi.set("project_name", os.getenv("OS_PROJECT_NAME"))
username = os.getenv("USER")

res = []
lease.add_device_reservation(res, machine_name="raspberrypi4-64", count=1)
start_date, end_date = lease.lease_duration(days=0, hours=10)
l = lease.create_lease(f"{username}-imp-lease", res,
                       start_date=start_date, end_date=end_date)
l = lease.wait_for_active(l["id"])

container_name = f"{username}-imp-ssh".replace("_", "-")
my_container = container.create_container(
    container_name,
    image="python:3.9-slim",
    reservation_id=lease.get_device_reservation(l["id"]),
    interactive=True,
    exposed_ports=[22],
    platform_version=2,
)
container.wait_for_active(my_container.uuid)
public_ip = container.associate_floating_ip(my_container.uuid)

container.execute(my_container.uuid, "apt update")
container.execute(my_container.uuid, "apt -y install openssh-server")
container.execute(my_container.uuid, "mkdir -p /root/.ssh")
container.upload(my_container.uuid, "./tmp_keys/authorized_keys", "/root/.ssh")
container.execute(my_container.uuid, "chmod 600 /root/.ssh/authorized_keys")
container.execute(my_container.uuid, "service ssh start")
print("ssh root@%s" % public_ip)
''',
    notes="Documented exception to the D01 OO anchor: the prompt itself demands "
          "the imperative generation."))

NEW.append(dict(
    id="N14", category="Uncovered peripheral", axis="REASON", lineage="new",
    prompt="I want to record audio from a USB microphone plugged into a CHI@Edge "
           "Raspberry Pi. Which device profile do I use and how do I set up the "
           "container?",
    trap="No audio profile is documented anywhere; the correct behavior is "
         "discovery or honest abstention, not a fabricated profile string.",
    target=[], fed=dict(blind=[], uncovered=["A1", "A2", "A3"]),
    intent=dict(uncovered="T4"),
    traps=["abstention", "magic_profile"],
    expected_answer_type="abstain_or_discover",
    tokens=dict(mechanism=["get_devices"], specifics=["microphone"]),
    checkers=[S("abstain_or_discover", "mechanism"), KNOWN_ONLY,
              S("forbidden_code_strings", "safety",
                strings=["pi_microphone", "pi_audio", "pi_mic", "usb_audio",
                         "audio_profile"])],
    gold='''from chi import hardware

# No public CHI@Edge artifact documents a microphone/audio device profile, and I
# cannot verify that one exists. The correct move is to inspect live inventory
# for the profiles devices actually support instead of guessing a profile string:
devs = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
for d in devs:
    print(d.device_name, d.supported_device_profiles)
# If no audio-related profile appears, this workload is not currently supported
# via device_profiles; ask the Chameleon help desk before proceeding.
'''))

NEW.append(dict(
    id="N15", category="Uncovered specifics", axis="READ", lineage="new",
    prompt="Reserve any free Raspberry Pi 5 on CHI@Edge by machine type for 3 "
           "hours.",
    trap="No artifact states the Pi-5 machine_type string (the Pi-5 tutorial "
         "leases via GUI UIDs); asserting one is fabrication - discover it.",
    target=["A5"], fed=dict(blind=[], matched=["A2", "A5"],
                            heldout=["A1", "A2", "A3"]),
    intent=dict(matched="T3", heldout="T4"),
    traps=["live_state", "magic_machine_type"],
    tokens=dict(mechanism=["get_devices", "add_device_reservation"],
                specifics=["nyu-rpi5"]),
    checkers=[S("required_call", "mechanism", name="get_devices"), DEV_RES,
              hours(3), NO_BAREMETAL],
    gold='''from chi import hardware, lease
from datetime import timedelta

# No artifact states the Pi-5 machine_type string; discover it from live
# inventory rather than guessing.
rpi5 = [d for d in hardware.get_devices(filter_reserved=True)
        if d.device_name.startswith("nyu-rpi5")]
print({d.device_type for d in rpi5})  # the real machine_type string

my_lease = lease.Lease("rpi5-lease", duration=timedelta(hours=3))
my_lease.add_device_reservation(devices=[rpi5[0]])
my_lease.submit(idempotent=True)
'''))

NEW.append(dict(
    id="N16", category="GPU / LLM", axis="REASON", lineage="new",
    prompt="Run GPU-accelerated inference on a Jetson-class device on CHI@Edge: "
           "reserve one and start a CUDA-capable container on it.",
    trap="Jetson device_type strings are not in the fed tutorials; GPU access on "
         "edge needs runtime='nvidia', which only one artifact shows.",
    target=["A4"], fed=dict(blind=[], matched=["A2", "A4"],
                            heldout=["A1", "A2", "A3"]),
    intent=dict(matched="T3", heldout="T4"),
    traps=["gpu_runtime", "live_state"],
    tokens=dict(mechanism=["get_devices", "add_device_reservation",
                           "reservation_id"],
                specifics=["runtime=\"nvidia\""]),
    checkers=[S("required_call", "mechanism", name="get_devices"), DEV_RES, CTR,
              WIRING, RUNTIME_NV, NO_BAREMETAL, NAME_OK],
    gold=f'''from chi import hardware, lease, container
from datetime import timedelta

# Jetson device_type strings are not documented in the tutorials; discover them.
devs = hardware.get_devices(filter_reserved=True)
jetsons = [d for d in devs if "jetson" in d.device_type.lower()
           or "jetson" in d.device_name.lower()]
print([(d.device_name, d.device_type) for d in jetsons])

my_lease = lease.Lease("jetson-gpu-lease", duration=timedelta(hours=4))
my_lease.add_device_reservation(devices=[jetsons[0]])
my_lease.submit(idempotent=True)

c = container.Container(
    name="jetson-infer",
    reservation_id=my_lease.device_reservations[0]["id"],
    image_ref="{OLLAMA_IMG}",
    runtime="nvidia",
    exposed_ports=[],
)
c.submit(idempotent=True)
'''))

NEW.append(dict(
    id="N17", category="Uncovered API", axis="REASON", lineage="new",
    prompt="My CHI@Edge lease expires in an hour; extend it by 2 more hours from "
           "python-chi.",
    trap="No artifact demonstrates lease extension; invented extend/renew methods "
         "are the failure mode.",
    target=[], fed=dict(blind=[], uncovered=["A1", "A2", "A3"]),
    intent=dict(uncovered="T4"),
    traps=["abstention"],
    expected_answer_type="abstain_or_discover",
    tokens=dict(mechanism=[], specifics=["extend the lease"]),
    checkers=[S("abstain_or_discover", "mechanism"),
              S("forbidden_calls", "safety",
                names=["extend_lease", "renew_lease", "update_lease", "extend",
                       "renew", "prolong"])],
    gold='''# Neither the CHI@Edge tutorials nor the python-chi surface shown in them
# demonstrates a lease-extension call, and I cannot confirm one exists.
# Verified options instead:
#   1. Horizon GUI: Reservations > Leases > Update Lease (change the end time), or
#   2. create a follow-on lease and move the container:
#      my_lease.delete(), then a fresh lease.Lease(...) + add_device_reservation(...)
# Check the current python-chi docs before trusting any extend/renew method name.
'''))

NEW.append(dict(
    id="N18", category="Uncovered peripheral", axis="REASON", lineage="new",
    prompt="Use a plain USB (UVC) webcam on a CHI@Edge Pi with OpenCV - what "
           "device profile and container setup do I need?",
    trap="pi_libcamera covers the CSI camera stack, not UVC; no UVC profile is "
         "documented - fabricating one is the failure mode.",
    target=[], fed=dict(blind=[], uncovered=["A1", "A2", "A3"]),
    intent=dict(uncovered="T4"),
    traps=["abstention", "magic_profile"],
    expected_answer_type="abstain_or_discover",
    tokens=dict(mechanism=["get_devices"], specifics=["webcam"]),
    checkers=[S("abstain_or_discover", "mechanism"), KNOWN_ONLY,
              S("forbidden_code_strings", "safety",
                strings=["pi_webcam", "usb_camera", "pi_usb", "uvc_camera",
                         "pi_uvc"])],
    gold='''from chi import hardware

# There is no documented CHI@Edge device profile for USB/UVC webcams in the
# public tutorials; pi_libcamera covers the CSI camera stack, not UVC. I cannot
# verify that a UVC path exists. Check what the devices actually expose:
devs = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
for d in devs:
    print(d.device_name, d.supported_device_profiles)
# If no UVC/audio-video profile appears, ask the Chameleon team; do not guess a
# profile string.
'''))


AV = [
    dict(
        id="AV01", category="Availability", axis="READ",
        prompt="Print the device_name of every raspberrypi4-64 device on CHI@Edge "
               "that is free to reserve right now (one per line).",
        trap="filter_reserved=False (or omitted) lists reserved devices too.",
        fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
        tokens=dict(mechanism=["get_devices", "filter_reserved"],
                    specifics=["raspberrypi4-64"]),
        checkers=[avail("raspberrypi4-64")],
        expect=dict(stdout_contains_all=["iot-rpi4-01", "iot-rpi4-03",
                                         "iot-rpi4-picam2", "iot-rpi4-picam3",
                                         "iot-rpi-cm4-02"],
                    stdout_not_contains=["iot-rpi4-02", "iot-rpi4-picam1",
                                         "nyu-rpi5"]),
        gold='''from chi import hardware

devs = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
for d in devs:
    print(d.device_name)
'''),
    dict(
        id="AV02", category="Availability", axis="READ",
        prompt="Print True if the device iot-rpi4-picam2 is free to reserve right "
               "now on CHI@Edge, otherwise print False.",
        trap="Static answers; direction bug on filter_reserved.",
        fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
        tokens=dict(mechanism=["get_devices", "filter_reserved"],
                    specifics=["iot-rpi4-picam2"]),
        checkers=[avail()],
        expect=dict(stdout_contains_all=["True"], stdout_not_contains=["False"]),
        gold='''from chi import hardware

devs = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
print(any(d.device_name == "iot-rpi4-picam2" for d in devs))
'''),
    dict(
        id="AV03", category="Availability", axis="READ",
        prompt="Print a single integer: how many CHI@Edge devices are free to "
               "reserve right now, across all device types.",
        trap="Counting all enrolled devices instead of free ones.",
        fed=dict(blind=[], matched=["A2"]), intent=dict(matched="T1"),
        tokens=dict(mechanism=["get_devices", "filter_reserved"], specifics=[]),
        checkers=[avail()],
        expect=dict(stdout_contains_all=["7"], stdout_not_contains=["10"]),
        gold='''from chi import hardware

devs = hardware.get_devices(filter_reserved=True)
print(len(devs))
'''),
    dict(
        id="AV04", category="Availability", axis="READ",
        prompt="Print the device_name of every currently-free CHI@Edge device that "
               "supports the pi_sensehat device profile.",
        trap="supported_device_profiles is not documented in the tutorials; "
             "guessing device names instead of filtering by profile.",
        fed=dict(blind=[], matched=["A2", "A3"]), intent=dict(matched="T4"),
        tokens=dict(mechanism=["get_devices", "filter_reserved"],
                    specifics=["supported_device_profiles"]),
        checkers=[avail(), cs("supported_device_profiles")],
        expect=dict(stdout_contains_all=["iot-rpi4-picam3"],
                    stdout_not_contains=["iot-rpi4-picam2", "iot-rpi-cm4-02"]),
        gold='''from chi import hardware

devs = hardware.get_devices(filter_reserved=True)
for d in devs:
    if "pi_sensehat" in d.supported_device_profiles:
        print(d.device_name)
'''),
]


# --------------------------------------------------------------------------
# Emit
# --------------------------------------------------------------------------

class _Lit(str):
    pass


def _lit_presenter(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(_Lit, _lit_presenter)


def emit(item, path):
    item = dict(item)
    for k in ("gold_spec", "prompt"):
        if "\n" in str(item.get(k, "")):
            item[k] = _Lit(item[k])
    path.write_text(yaml.dump(item, sort_keys=False, width=100,
                              allow_unicode=True))


def main():
    out = ROOT / "items"
    out.mkdir(exist_ok=True)
    for p in out.glob("*.yaml"):
        p.unlink()

    v3 = {json.loads(l)["id"]: json.loads(l)
          for l in (ROOT / "tools" / "v3_prompts.jsonl").read_text().splitlines()
          if l.strip() and '"id"' in l}

    count = 0
    for pid, ov in V3.items():
        src = v3[pid]
        item = {
            "id": pid, "version": "4.0", "lineage": f"v3:{pid}",
            "category": src["cat"], "axis": src["axis"],
            "prompt": src["prompt"],
            "designed_trap": src["trap"],
            "trap_tags": ov["traps"],
            "target_artifact": ov["target"],
            "fed_sets": ov["fed"],
            "tier_intent_by_condition": ov["intent"],
            "key_tokens": ov["tokens"],
            "api_anchor": "python-chi OO generation (D01); imperative accepted "
                          "at full credit iff trap-free",
            "verification_level": "V0",
            "expected_answer_type": ov.get("expected_answer_type", "code"),
            "gold_spec": ov["gold"],
            "gold_provenance": f"authored from artifact(s) {ov['target']} "
                               f"extractions; v3 gold: {src['gold']}",
            "checkers": ov["checkers"],
        }
        if ov.get("notes"):
            item["notes"] = ov["notes"]
        emit(item, out / f"{pid}.yaml")
        count += 1

    for n in NEW:
        item = {
            "id": n["id"], "version": "4.0", "lineage": n["lineage"],
            "category": n["category"], "axis": n["axis"],
            "prompt": n["prompt"],
            "designed_trap": n["trap"],
            "trap_tags": n["traps"],
            "target_artifact": n["target"],
            "fed_sets": n["fed"],
            "tier_intent_by_condition": n["intent"],
            "key_tokens": n["tokens"],
            "api_anchor": "python-chi OO generation (D01)"
                          + ("; item demands imperative (documented exception)"
                             if n["id"] == "N13" else ""),
            "verification_level": "V0",
            "expected_answer_type": n.get("expected_answer_type", "code"),
            "gold_spec": n["gold"],
            "gold_provenance": f"authored from artifact(s) {n['target'] or 'none (uncovered)'}",
            "checkers": n["checkers"],
        }
        if n.get("notes"):
            item["notes"] = n["notes"]
        emit(item, out / f"{n['id']}.yaml")
        count += 1

    for a in AV:
        item = {
            "id": a["id"], "version": "4.0", "lineage": "new",
            "category": a["category"], "axis": a["axis"],
            "prompt": a["prompt"],
            "designed_trap": a["trap"],
            "trap_tags": ["live_state"],
            "target_artifact": ["A2"],
            "fed_sets": a["fed"],
            "tier_intent_by_condition": a["intent"],
            "key_tokens": a["tokens"],
            "api_anchor": "python-chi OO generation (D01)",
            "verification_level": "V1",
            "expected_answer_type": "code",
            "v1_expect": a["expect"],
            "gold_spec": a["gold"],
            "gold_provenance": "get_devices pattern from A2; Device fields from "
                               "the advisor prototype probe",
            "checkers": a["checkers"],
        }
        emit(item, out / f"{a['id']}.yaml")
        count += 1

    print(f"emitted {count} items -> {out}")


if __name__ == "__main__":
    main()
