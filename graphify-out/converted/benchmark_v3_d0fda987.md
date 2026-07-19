<!-- converted from benchmark_v3.xlsx -->

## Sheet: README
|  | CHI@Edge Coding Benchmark |  |
| --- | --- | --- |
|  | What this is | CHI@Edge coding prompts. Each gold answer was read straight from the notebook of the Trovi artifact it maps to — so the artifact provably contains the answer. Grounded only in the 3 artifacts that have public, readable repos: SSH, Pi Camera, Sense HAT. |
|  | The setups | S1 Chatbot (blind) , S1 Chatbot (artifact), S2 GPT (blind), S2 GPT (artifact), S3 Claude Sonnet (blind), S3 Claude Sonnet (artifact), 28 prompts × 6 = 168 runs. |
|  | Blind vs artifact | Blind = paste the prompt only, fresh Incognito/Temporary chat. Artifact = paste the mapped artifact's notebook + README first, then the same prompt. The blind→artifact lift is the headline result. |
|  | Where to work | Outputs' is the data-entry sheet (140 pre-filled rows). Paste each reply, the screenshot filename, and a 0–2 score. 'Summary' aggregates automatically. 'Benchmark' is the read-only prompt bank + gold. 'Artifacts' lists the 3 sources with verified links. |
|  | Scoring (0–2) | 2 = runnable as-is, all traps avoided · 1 = right shape, one fixable error or one trap missed · 0 = wrong API, won't run, or hallucinated function/profile. Blank = not yet graded (Summary ignores blanks). |
|  | Two API styles — accept either | Current artifacts use two python-chi styles: object-oriented (lease.Lease(...).submit(), container.Container(...)) in Camera/Sense HAT, and functional (create_lease, create_container) in SSH. Gold is written in whichever style its source notebook uses, but a correct answer in EITHER style scores full marks if it would run. |
|  | Eval axes | READ = needs live state (availability) · REASON = workload→resource decision · VALIDATE = catches a CHI@Edge pitfall · ACT = emits a valid spec. |
|  | Screenshot naming | Files named by ID + setup, e.g. P16_S2-blind.png, P16_S2-artifact.png. |
## Sheet: Benchmark
| ID | Category | Diff. | Axis | Prompt (paste verbatim) | Designed trap / pitfall | Gold answer (1–2 lines) | Artifact |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | Setup | E | ACT | Show the minimal python-chi setup to target CHI@Edge and select my project. | chi.use_site vs context; wrong site string; forgets project. | context.choose_site(default="CHI@Edge"); context.choose_project()  — or chi.use_site("CHI@Edge") + chi.set("project_name", ...) | A1/A2 |
| P02 | Reservation | E | ACT | Reserve one Raspberry Pi 4 on CHI@Edge for 2 hours. | Bare-metal add_node_reservation / node_type. | lease.Lease("n", duration=timedelta(hours=2)); .add_device_reservation(machine_type="raspberrypi4-64", amount=1); .submit() | A3 |
| P03 | Reservation | M | ACT | Reserve a Pi on CHI@Edge and get the reservation_id I'll pass to a container. | Never retrieves the id; wrong attribute. | After submit: my_lease.device_reservations[0]["id"] | A2 |
| P04 | Reservation | M | ACT | Reserve 3 Raspberry Pis on CHI@Edge of the same type in one lease. | Node reservation; count mishandled. | .add_device_reservation(machine_type="raspberrypi4-64", amount=3) | A3 |
| P05 | Container | E | ACT | Launch a basic Ubuntu container on a reserved Pi on CHI@Edge. | create_server (VM) instead of a container. | container.Container(name, image_ref="ubuntu:22.04", reservation_id=rid).submit()  (name: no underscores — k8s) | A2 |
| P06 | Container | E | VALIDATE | My container on CHI@Edge exits immediately. Make it stay running so I can exec into it. | No long-running command given. | Add command=["sleep","infinity"] to Container(...) | A2 |
| P07 | Container | M | ACT | Expose port 8080 on my CHI@edge container and give it a public IP. | exposed_ports string format; FIP omitted; nova idioms. | exposed_ports=[8080] in the container; then chi.container.associate_floating_ip(c.uuid) | A1 |
| P08 | Container | M | ACT | Run 'ls /app' inside the running container in CHI@Edge and capture the output. | Hallucinated exec API; ignores tuple return. | result, code = my_container.execute("ls /app") | A2 |
| P09 | Container | E | ACT | Upload model.pt into the CHI@Edge container, then download results.csv back out. | Invented up/download names. | my_container.upload("model.pt", "/app/"); my_container.download("/app/results.csv", ".") | A2 |
| P10 | Container | E | ACT | Tear everything down: remove the CHI@Edge container and free the device. | Invented teardown; leaves the lease. | my_container.delete(); my_lease.delete() | A2 |
| P11 | SSH / Dev | M | ACT | Launch an SSH-enabled container on a reserved Pi and tell me how to connect. | Doesn't know edge_ssh_image; wrong port type. | Container(image_ref="ghcr.io/chameleoncloud/edge_ssh_image:latest", exposed_ports=[22], ...); associate_floating_ip -> ssh root@<ip> | A1 |
| P12 | SSH / Dev | M | VALIDATE | Inject my public key so I can SSH in as root. | Wrong key path / mechanism. | upload pubkey to /root/.ssh/; execute chmod 600 authorized_keys; cat key >> /root/.ssh/authorized_keys | A1 |
| P13 | SSH / Dev | E | VALIDATE | Which image and exposed port do I need for SSH on CHI@Edge? | Generic sshd build; misses prebuilt image. | ghcr.io/chameleoncloud/edge_ssh_image:latest, exposed_ports=[22] | A1 |
| P14 | SSH / Dev | H | REASON | End-to-end: get me a Pi on CHI@Edge I can hit with VS Code Remote-SSH. | Drops a link in reserve->image->key->FIP chain. | reserve Pi -> Container(edge_ssh_image, exposed_ports=[22]) -> upload+authorize key -> associate_floating_ip -> VS Code to root@ip | A1 |
| P15 | Peripherals · Camera | M | READ | Find which Pis have a camera attached and reserve one. | Can't filter by peripheral; guesses device. | hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64"); pick device_name starting "iot-rpi4-picam"; add_device_reservation(devices=[dev]) | A2 |
| P16 | Peripherals · Camera | M | VALIDATE | Launch a container with the Pi camera enabled. | Omits device_profiles; guesses the profile name. | Container(image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest", device_profiles=["pi_libcamera"], command=["sleep","infinity"]) | A2 |
| P17 | Peripherals · Camera | M | ACT | Capture a 1080p still from the Pi Camera and download it. | Made-up capture API; no download. | execute("rpicam-still --nopreview --output /app/x.png --width 1920 --height 1080"); download("/app/x.png", ".") | A2 |
| P18 | Peripherals · Camera | M | ACT | Record a 5-second 1080p video from the camera. | Wrong tool / flags. | execute("rpicam-vid --nopreview -t 5000 --output /app/v.mp4 --width 1920 --height 1080 --framerate 24") | A2 |
| P19 | Peripherals · Camera | E | VALIDATE | Verify the camera is detected inside the container. | Invents a detection command. | execute("rpicam-hello --nopreview --list-cameras") | A2 |
| P20 | Peripherals · Sense HAT | M | ACT | Reserve the specific device that has the Sense HAT attached. | Reserves any device; ignores device_name. | add_device_reservation(amount=1, machine_type="raspberrypi4-64", device_name="iot-rpi4-picam3") | A3 |
| P21 | Peripherals · Sense HAT | M | VALIDATE | Launch a container with the Sense HAT enabled. | Omits / guesses the device profile. | Container(image_ref="ghcr.io/chameleoncloud/edge_sensehat_image:latest", device_profiles=["pi_sensehat"], command=["-c","sleep infinity"]) | A3 |
| P22 | Peripherals · Sense HAT | M | ACT | Read temperature, humidity and pressure from the Sense HAT. | Assumes host access; wrong library. | execute python: from sense_hat import SenseHat; .get_temperature_from_humidity()/.get_humidity()/.get_pressure() | A3 |
| P23 | Peripherals · Sense HAT | M | VALIDATE | From inside the container, list the I2C addresses to debug the sensor bus. | No I2C access path. | execute("i2cdetect -y 1")  (needs the pi_sensehat profile exposing /dev/i2c-*) | A3 |
| P24 | Peripherals · Sense HAT | E | VALIDATE | Which device profile and image do I use for Sense HAT / GPIO work? | Guesses the profile string. | device_profiles=["pi_sensehat"], image ghcr.io/chameleoncloud/edge_sensehat_image:latest | A3 |
| P25 | Availability | M | READ | List which CHI@Edge device types currently exist and are reservable. | Lists bare-metal flavors; invents an endpoint. | hardware.get_devices(filter_reserved=True); inspect device_type / device_name (Blazar-backed). | A2 |
| P26 | Availability | H | READ | Before reserving on CHI@Edge, check whether a given device is free right now. | Claims it has no live state; fabricates an API. | hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64") — a free device in the result means it's available. | A2 |
| P27 | Availability | M | READ | How do I find which device_profiles a device supports? | Guesses a call. | The artifact README documents the device's profile (e.g. pi_libcamera, pi_sensehat); pass it via device_profiles. | A3 |
| P28 | Pitfall trap | H | VALIDATE | Convert my CHI@UC bare-metal script (add_node_reservation, node_type='compute_skylake', create_server) to run on CHI@Edge. | Keeps node/flavor/server. | Swap to device reservation (add_device_reservation/machine_type) + container.Container(image_ref, reservation_id).submit(); drop flavor/keypair/network; site CHI@Edge. | A1 |
## Sheet: Artifacts
| Key | Title | Trovi link | Backing GitHub repo (read in full) | What it grounds |
| --- | --- | --- | --- | --- |
| A1 | SSH on CHI@Edge | https://trovi.chameleoncloud.org/dashboard/artifacts/4b08e80c-df0a-4866-bf29-19b5ad6a2950 | https://github.com/ChameleonCloud/edge_ssh_image | Setup, lease + device reservation, container launch, exposed port 22, public-key injection, FIP, exec, teardown, bare-metal→edge translation |
| A2 | Pi Camera Module 3 | https://trovi.chameleoncloud.org/dashboard/artifacts/7d35f884-68d8-4b91-b42b-207717c9b742 | https://github.com/ChameleonCloud/edge-picamera-image | context.choose_site, hardware.get_devices() availability query, Lease + add_device_reservation(devices), Container device_profiles=['pi_libcamera'], capture still/video, download/upload |
| A3 | Sensors & GPIO (Sense HAT) | https://trovi.chameleoncloud.org/dashboard/artifacts/1b8cdcba-e10c-4cae-8b1e-145037bc4cda | https://github.com/ChameleonCloud/edge_sensehat_image | Lease + add_device_reservation(device_name), Container device_profiles=['pi_sensehat'], read sensors via sense_hat, i2cdetect / GPIO, profile+image selection |
## Sheet: Output
| ID | Category | Setup | Model output (paste here) | Screenshot file | Score (0–2) | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| P01 | Setup | S1 · Chatbot (blind) | To target CHI@Edge and select your project using python-chi, you can use the following minimal setup:

import chi
chi.use_site("CHI@Edge")
chi.use_project("CHI-XXXXXX")  # Replace with your project name

This code imports the python-chi module, sets the site to CHI@Edge, and sets the active project. Replace "CHI-XXXXXX" with your actual project name.

Alternatively, you can use interactive dropdown menus in a Jupyter Notebook:

import chi
chi.context.choose_site()
chi.context.choose_project()

Further Reading
DocsJupyter Python Chi
DocsGui |  | 2 | Gives both styles correctly; direct and concise. 'Further Reading' appended. |
| P01 | Setup | S1 · Chatbot (artifact) | To target CHI@Edge and select your project using python-chi, you can use the following minimal setup:

import chi
chi.use_site("CHI@Edge")
chi.set("project_name", "Your_Project_Name")

Replace "Your_Project_Name" with the actual name of your project. This will set up the python-chi library to use the CHI@Edge site and your specified project.

Further Reading
DocsGui
BlogChi In A Box Update
DocsFederation
DocsGetting Started
BlogSeamless Ssh Container Access With Chiedge
BlogBack To School With Chameleon |  | 2 | Correct, matches artifact's exact style. |
| P01 | Setup | S2 · GPT (blind) | A minimal python-chi setup for CHI@Edge is:

from chi import context

# Select the CHI@Edge site
context.use_site("CHI@Edge")

# Select your project
context.use_project("your-project-name")

If you prefer using a project ID:

from chi import context

context.use_site("CHI@Edge")
context.use_project("project-id")

A slightly more complete example that verifies the active context:

from chi import context

context.use_site("CHI@Edge")
context.use_project("your-project-name")

print("Site:", context.site())
print("Project:", context.project())

Before running this, authenticate with your Chameleon credentials (typically via an application credential or sourced OpenStack RC file, depending on your environment). After use_site() and use_project(), subsequent python-chi operations will target CHI@Edge under the selected project. |  | 1 | Invents context.use_project() — looks plausible but not a real python-chi API. |
| P01 | Setup | S2 · GPT (artifact) | Based on the artifact, the minimal python-chi setup to target CHI@Edge and select your project is:

import chi

# Select the CHI@Edge site
chi.use_site("CHI@Edge")

# Select your project
chi.set("project_name", "Chameleon")

This is the exact setup used in the notebook before any lease or container operations:

import chi

chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")

from chi import container
from chi import lease

The artifact explicitly uses:

Site: chi.use_site("CHI@Edge")
Project: chi.set("project_name", "Chameleon")

After these two calls, you can proceed with lease creation (lease.create_lease) and container deployment (container.create_container) on CHI@Edge. |  | 2 | Verbatim from artifact; correct. |
| P01 | Setup | S3 · Claude (blind) | pythonimport chi

chi.use_site("CHI@Edge")
chi.set("project_name", "YOUR_PROJECT_NAME")  # e.g. "CHI-XXXXXX"
That's it — use_site points the client at the CHI@Edge API endpoint, and set("project_name", ...) selects which Chameleon project/allocation your subsequent calls (leases, containers, devices, etc.) run under.
A couple of notes:

Project name is usually the CHI-XXXXXX charge code shown on the Chameleon portal, not your username.
You'll also need to be authenticated (e.g. via an application_credential set as OS_* env vars or chi.set("auth", {...})) before site/project selection actually does anything useful — let me know if you want that part too. |  | 2 | Correct + helpful note about auth credentials. |
| P01 | Setup | S3 · Claude (artifact) | Based on the artifact, the minimal python-chi setup to target CHI@Edge and select your project is:

import chi

# Select the CHI@Edge site
chi.use_site("CHI@Edge")

# Select your project
chi.set("project_name", "Chameleon")

This is the exact setup used in the notebook before any lease or container operations:

import chi

chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")

from chi import container
from chi import lease

The artifact explicitly uses:

Site: chi.use_site("CHI@Edge")
Project: chi.set("project_name", "Chameleon")

After these two calls, you can proceed with lease creation (lease.create_lease) and container deployment (container.create_container) on CHI@Edge. |  | 2 | Identical to GPT artifact; verbatim from artifact. |
| P02 | Reservation | S1 · Chatbot (blind) | To reserve one Raspberry Pi 4 on CHI@Edge for 2 hours, you can use the following Python code with the python-chi library:

import chi

# Create authentication context (most info automatically sourced from env)
chi.use_site('CHI@Edge')

# Define the lease parameters
lease_name = "my-lease"
node_type = "Raspberry Pi 4"  # Ensure this is the correct node type for Raspberry Pi 4
node_count = 1
hours = 2

# Request a lease for nodes
reservations = []
chi.lease.add_node_reservation(reservations, count=node_count, node_type=node_type)

# Define the lease duration
start_date, end_date = chi.lease.lease_duration(hours=hours)

# Create the lease
lease = chi.lease.create_lease(lease_name, reservations, start_date=start_date, end_date=end_date)

# Wait for the lease to become active
chi.lease.wait_for_active(lease.id)

This code will create a lease for one Raspberry Pi 4 node on CHI@Edge for 2 hours. Please ensure that the node_type parameter is set to the correct value for Raspberry Pi 4 nodes on CHI@Edge. Also, note that you need to have the necessary credentials and environment variables set up to use the python-chi library.

Further Reading
BlogCloud Wrangling Chameleons Python Library |  | 0 | Falls into bare-metal trap: add_node_reservation + node_type. |
| P02 | Reservation | S1 · Chatbot (artifact) | o reserve one Raspberry Pi 4 on CHI@Edge for 2 hours, you can use the following Python code with the python-chi library:

from chi import lease
import os

# Set the site
chi.context.use_site("CHI@Edge")
chi.context.choose_project()  # Comment this line if running outside JupyterHub

# machine name refers to the "type" of device
machine_name = "raspberrypi4-64"

# Reserving the specific device
device_name = "iot-rpi4-picam3"  # Replace with your desired device name

# make a unique name for the lease
username = os.environ.get("USER")
lease_name = f"{username}-{device_name}"
container_lease = lease.Lease(name=lease_name, duration=lease.timedelta(hours=2))
container_lease.add_device_reservation(
    amount=1, machine_type=machine_name, device_name=device_name
)
container_lease.submit()
print("Done!")

Remember to replace "iot-rpi4-picam3" with your desired device name. Also, make sure you have the necessary permissions and that the device is available for reservation.

After you're done with the reservation, don't forget to delete the lease to free up the device:

# deleting the lease will free up the device now, instead of waiting for it to expire later
container_lease.delete()

Further Reading
DocsGui
BlogChi In A Box Update
BlogExperiment Patterns Making Complex Experiments Easy
BlogPackaging Your Experiments On Chameleon With Python Chi 10
BlogConducting Research On The Edge Chiedge
DocsGetting Started |  | 2 | Correct API; over-pins to camera device from artifact; small typo. |
| P02 | Reservation | S2 · GPT (blind) | I cannot directly access CHI@Edge or make reservations on your behalf.

To reserve a Raspberry Pi 4 on CHI@Edge:

Log in to the CHI portal.
Go to CHI@Edge resources.
Open the Reservations interface.
Select a Raspberry Pi 4 node.
Set the reservation duration to 2 hours.
Submit the reservation request.

If you provide the reservation page details, available nodes, or any error message you're seeing, I can help you complete the process. |  | 0 | Refuses to write code; portal steps only. |
| P02 | Reservation | S2 · GPT (artifact) | To reserve one Raspberry Pi 4 on CHI@Edge for 2 hours, use the same lease workflow shown in the artifact, but set the lease duration to 2 hours instead of 4. The artifact uses machine_type="raspberrypi4-64" and creates a device reservation with amount=1.

import chi
from chi import lease
import os

# Authenticate
chi.context.use_site("CHI@Edge")
chi.context.choose_project()

# Raspberry Pi 4 machine type
machine_name = "raspberrypi4-64"

# Choose a specific device
device_name = "iot-rpi4-picam3"

username = os.environ.get("USER")
lease_name = f"{username}-{device_name}"

# Reserve for 2 hours
container_lease = lease.Lease(
    name=lease_name,
    duration=lease.timedelta(hours=2)
)

container_lease.add_device_reservation(
    amount=1,
    machine_type=machine_name,
    device_name=device_name
)

container_lease.submit()

print("Lease created:", lease_name)

The authentication method, machine type, and reservation API calls are taken directly from the CHI@Edge artifact. |  | 2 | Correct API; mirrors artifact closely. |
| P02 | Reservation | S3 · Claude (blind) | There's no MCP connector available for Chameleon Cloud / CHI@Edge. However, I can guide you through making the reservation yourself via the CHI@Edge web portal or the CLI.

Reserving a Raspberry Pi 4 on CHI@Edge
Option 1: Web Portal (Easiest)

Log in at chi.edge.chameleoncloud.org with your Chameleon account.
Go to Reservations → Leases in the left sidebar.
Click + Create Lease and fill in:

Lease name: anything you like (e.g. my-rpi4-test)
Start time: now (or a specific time)
End time: start + 2 hours


Under Resources, click Add Resource:

Resource type: Device
Filter by device_type = rpi4 (or search for raspberry in the node filter)
Set min/max count to 1


Click Create Lease and wait for it to move to ACTIVE status.


Option 2: CLI with blazar (python-blazarclient)
bash# Install if needed
pip install python-blazarclient python-openstackclient

# Source your CHI@Edge OpenRC file first
source ~/chi-edge-openrc.sh

# Create a 2-hour lease for 1 Raspberry Pi 4
openstack reservation lease create \
  --reservation resource_type=device,resource_properties='["=","$device_type","rpi4"]',min=1,max=1 \
  --start-date "$(date -u '+%Y-%m-%d %H:%M')" \
  --end-date "$(date -u -d '+2 hours' '+%Y-%m-%d %H:%M')" \
  my-rpi4-lease

Note: On macOS, use gdate (from GNU coreutils) instead of date -d.


After Your Lease is Active
Once the lease shows ACTIVE, you can enroll the device and SSH into it via the CHI@Edge console or by using the assigned floating IP.
Would you like help with any of the next steps — like launching a container on the reserved node? |  | 0 | Switches to openstack/Blazar CLI; no python-chi answer. |
| P02 | Reservation | S3 · Claude (artifact) | Here's the code to reserve a Raspberry Pi 4 on CHI@Edge for 2 hours, based on the artifact's patterns:
pythonimport chi
from chi import lease
import os

# Authenticate
chi.context.use_site("CHI@Edge")
chi.context.choose_project()  # comment out if running outside JupyterHub

# Device configuration
machine_name = "raspberrypi4-64"
device_name = "iot-rpi4-picam3"  # change to "iot-rpi4-picam2" or "iot-rpi-cm4-02" if unavailable

# Create a unique lease name
username = os.environ.get("USER")
lease_name = f"{username}-{device_name}"

# Create and submit the lease for 2 hours
container_lease = lease.Lease(name=lease_name, duration=lease.timedelta(hours=2))
container_lease.add_device_reservation(
    amount=1,
    machine_type=machine_name,
    device_name=device_name
)
container_lease.submit()
print("Done!")
A few notes:

machine_type is always "raspberrypi4-64" for RPi 4 devices on CHI@Edge — it refers to the device type, not a specific unit.
device_name pins the reservation to a specific physical board. The artifact lists three options (iot-rpi4-picam3, iot-rpi4-picam2, iot-rpi-cm4-02); swap in whichever is available.
Duration is changed to hours=2 from the artifact's default of 4.
Once done, free the device early with container_lease.delete() rather than waiting for expiry. |  | 2 | Correct API; helpful notes on device alternatives. |
| P03 | Reservation | S1 · Chatbot (blind) | To reserve a Pi on CHI@Edge and get the reservation_id, you can use the python-chi library. Here's a step-by-step guide:

Import the chi library and set the site to CHI@Edge: chi.use_site('CHI@Edge')
Define the parameters for your lease:
lease_name: the name of your lease
node_type: the type of node you want to reserve (e.g., "pi")
node_count: the number of nodes you want to reserve
Create a list to hold your reservations: reservations = []
Add a node reservation to your list: chi.lease.add_node_reservation(reservations, count=node_count, node_type=node_type)
Define the duration of your lease: start_date, end_date = chi.lease.lease_duration(hours=1)
Create the lease: lease = chi.lease.create_lease(lease_name, reservations, start_date=start_date, end_date=end_date)
Wait for the lease to become active: chi.lease.wait_for_active(lease.id)
Get the reservation_id: reservation_id = get_node_reservation(lease.id)
Note that the get_node_reservation function is not defined in the provided context, so you may need to implement this function or use a different method to get the reservation_id.

Also, make sure to replace "pi" with the actual node type for the Pi you want to reserve, and adjust the node_count and lease duration as needed.

Further Reading
BlogCloud Wrangling Chameleons Python Library |  | 0 | Bare-metal trap + admits it invented get_node_reservation(). |
| P03 | Reservation | S1 · Chatbot (artifact) | To reserve a Pi on CHI@Edge and get the reservation_id to pass to a container, you can follow these steps based on the provided context:

Choose the Site and Project: Start by selecting the CHI@Edge site and your project using the context.choose_site and context.choose_project functions from the python-chi library.

Get Available Devices: Use the hardware.get_devices function to retrieve a list of available devices that match your requirements, such as Raspberry Pi 4 devices with a Pi Camera Module 3 attached. Filter these devices based on their type and name.

Create a Lease: Create a lease for the desired device using the lease.Lease function. Specify the lease name, duration, and add a device reservation for the selected device.

Submit the Lease: Submit the lease to reserve the device. Wait for the lease to become active if necessary.

Get the Reservation ID: Once the lease is active, you can obtain the reservation ID from the lease object. This ID will be used to launch a container against the reserved device.

Here's a simplified example based on the provided context:

from chi import context, hardware, lease
from datetime import timedelta

# Choose the site and project
context.choose_site(default="CHI@Edge")
context.choose_project()

# Get available devices
device_type = "raspberrypi4-64"
available_devices = hardware.get_devices(filter_reserved=True, device_type=device_type)
picamera_devs = [d for d in available_devices if d.device_name.startswith("iot-rpi4-picam")]

# Create a lease
my_lease = lease.Lease("rpi4-camera-lease", duration=timedelta(hours=3))
my_lease.add_device_reservation(devices=[picamera_devs[0]])
my_lease.submit(idempotent=True)

# Wait for the lease to become active if necessary
# ...

# Get the reservation ID
reservation_id = my_lease.device_reservations[0]["id"]

This example demonstrates how to reserve a Raspberry Pi device on CHI@Edge and obtain the reservation ID, which can then be used to launch a container against the reserved device.

Further Reading
DocsGui
BlogChi In A Box Update
BlogCloud Wrangling Chameleons Python Library
BlogThe Hitchhikers Guide To Chameleon Documentation Finding Answers Fast
BlogTrovi Google Drive Chameleon Experiments
BlogConducting Research On The Edge Chiedge

 |  | 2 | Perfect — correct hardware.get_devices + device_reservations[0]['id']. |
| P03 | Reservation | S2 · GPT (blind) | I can't directly access or operate CHI@Edge, so I can't create a reservation or retrieve a real reservation_id.

If you have CLI or portal access, run the reservation and paste the output here. For example, with the CHI CLI:

chi lease create \
  --node-type raspberrypi \
  --name my-pi-reservation

or the equivalent command/workflow you use in CHI@Edge.

Once you have the reservation details, send me the output and I can help extract the reservation_id and show how to pass it into your container. |  | 0 | Refuses; suggests CHI CLI workaround; no API code. |
| P03 | Reservation | S2 · GPT (artifact) | I cannot create a CHI@Edge reservation from here or retrieve a live reservation_id from your project.

According to the artifact, the reservation is created by:

from chi import hardware, lease
from datetime import timedelta

device_type = "raspberrypi4-64"
available_devices = hardware.get_devices(
    filter_reserved=True,
    device_type=device_type
)

picamera_devs = [
    d for d in available_devices
    if d.device_name.startswith("iot-rpi4-picam")
]

my_lease = lease.Lease(
    "rpi4-camera-lease",
    duration=timedelta(hours=3)
)

my_lease.add_device_reservation(devices=[picamera_devs[0]])
my_lease.submit(idempotent=True)

reservation_id = my_lease.device_reservations[0]["id"]
print(reservation_id)

The artifact shows that:

Camera-capable devices are selected from device_type="raspberrypi4-64" and filtered by names beginning with iot-rpi4-picam.
A 3-hour lease is created and submitted.
The container later uses reservation_id=my_lease.device_reservations[0]["id"].

Once my_lease.submit(idempotent=True) completes, use:

reservation_id = my_lease.device_reservations[0]["id"]

and pass that value to your container.Container(...) call. |  | 2 | Mirrors artifact exactly; correct API. |
| P03 | Reservation | S3 · Claude (blind) | No MCP connector for Chameleon Cloud exists in the registry. I can help you do this directly via the CHI@Edge API (Blazar reservations) using Python in the terminal. You'll need your Chameleon credentials handy.
Here's what I'll run — it uses the chi Python SDK to create a reservation for a Raspberry Pi node on CHI@Edge:Ran 3 commandsRan 3 commandsGood — python-chi is installed. Now, to actually make the reservation I need a few things from you:

To proceed, I need:

OS_AUTH_TOKEN — your Chameleon Keystone token

(Get it from the CHI@Edge dashboard → Identity → Application Credentials, or run openstack token issue -f value -c id locally after sourcing your openrc.sh)
OS_PROJECT_ID — your project's UUID

(Visible in the CHI@Edge dashboard URL or in your openrc.sh as OS_PROJECT_ID)
Reservation window — start/end times in UTC, e.g. 2026-06-22T20:00:00 → 2026-06-22T22:00:00

(Minimum 1 hour; CHI@Edge uses Blazar leases)
Node type (optional, defaults to pi4): pi4 or pi3


Once you share those, I'll run a script like this to create the lease and return your reservation_id:
pythonimport chi
from chi import lease

chi.set("project_id", "<YOUR_PROJECT_ID>")
chi.set("region_name", "CHI@Edge")

new_lease = lease.create_lease(
    "my-pi-reservation",
    reservations=[lease.device_reservation(count=1, machine_type="pi4")],
    start_date="2026-06-22T20:00",
    end_date="2026-06-22T22:00",
)

reservation_id = lease.get_device_reservation(new_lease["id"])
print(f"reservation_id: {reservation_id}")
Tip: If you have your openrc.sh handy, you can paste its contents (redact passwords if you like) and I can parse the credentials automatically. |  | 0 | Invents incorrect API; asks for credentials; confused flow. |
| P03 | Reservation | S3 · Claude (artifact) | Here's the code to reserve a Pi Camera device and extract the reservation_id:
pythonfrom chi import context, hardware, lease
from datetime import timedelta

# 1. Set site and project
context.choose_site(default="CHI@Edge")
context.choose_project()

# 2. Find an available Pi Camera device
available_devices = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
picamera_devs = [d for d in available_devices if d.device_name.startswith("iot-rpi4-picam")]

print("Available Pi Camera devices:", [d.device_name for d in picamera_devs])

# 3. Create and submit the lease
my_lease = lease.Lease("rpi4-camera-lease", duration=timedelta(hours=3))
my_lease.add_device_reservation(devices=[picamera_devs[0]])
my_lease.submit(idempotent=True)

# 4. Extract the reservation_id
reservation_id = my_lease.device_reservations[0]["id"]
print("reservation_id:", reservation_id)
What each step does:

filter_reserved=True — only returns devices not currently reserved (i.e., available to you)
startswith("iot-rpi4-picam") — narrows to the Pi Camera–equipped nodes specifically
idempotent=True — safe to re-run; won't create a duplicate lease if one with that name already exists
device_reservations[0]["id"] — this is the reservation_id you'll pass to container.Container(..., reservation_id=..., device_profiles=["pi_libcamera"])

A few things to watch for:

If picamera_devs comes back empty, all camera-equipped Pis are currently reserved — you'll need to wait or check the CHI@Edge availability calendar.
You can pin a specific device instead of [0] by swapping the add_device_reservation call: my_lease.add_device_reservation(device_name='iot-rpi4-picam2', amount=1)
The lease runs for 3 hours; adjust duration= if you need more time.
 |  | 2 | Correct API; well-organized; matches gold exactly. |
| P04 | Reservation | S1 · Chatbot (blind) | To reserve 3 Raspberry Pis on CHI@Edge of the same type in one lease, you can follow these steps based on the Chameleon Cloud documentation:

Check Availability: First, ensure that the desired type of Raspberry Pi is available on CHI@Edge. You can do this by querying the CHI@Edge API for available resources.

Create a Lease: Use the CHI client or API to create a new lease. Specify the start and end times for your lease, ensuring you have enough time to complete your work.

Add Resources to Lease: Once the lease is created, you can add the desired Raspberry Pi resources to it. Since you want 3 Raspberry Pis of the same type, you will need to specify the resource type and the quantity (in this case, 3).

Confirm the Reservation: After adding the resources, confirm that your lease has been successfully created and that it includes the 3 Raspberry Pis you requested. You can do this by querying the lease details through the CHI client or API.

Here's a simplified example using the Python CHI client, assuming you have it installed and configured:

from chi import Client

# Initialize the CHI client
client = Client()

# Define your lease and resources
lease_name = "my_rpi_lease"
start_time = "2023-04-01T12:00:00Z"
end_time = "2023-04-02T12:00:00Z"
resource_type = "rpi4"  # Example resource type, replace with actual type
quantity = 3

# Create the lease
lease = client.create_lease(lease_name, start_time, end_time)

# Add resources to the lease
client.add_resources_to_lease(lease.id, resource_type, quantity)

# Confirm the lease details
lease_details = client.get_lease(lease.id)
print(lease_details)

This example provides a basic outline. The actual implementation may vary depending on the specifics of your environment and the exact capabilities of the CHI@Edge and CHI client versions you are using. Always refer to the most current documentation for the most accurate and detailed instructions. |  | 0 | Entirely fabricated API (chi.Client, add_resources_to_lease). |
| P04 | Reservation | S1 · Chatbot (artifact) | To reserve 3 Raspberry Pis on CHI@Edge of the same type in one lease, you can use the following Python code with the python-chi library:

from chi import lease
import os

# machine name refers to the "type" of device
machine_name = "raspberrypi4-64"

# Reserving the specific devices
device_name = "iot-rpi4-picam3" # example device name

# make a unique name for the lease
username = os.environ.get("USER")
lease_name = f"{username}-{device_name}"
container_lease = lease.Lease(name=lease_name, duration=lease.timedelta(hours=4))
container_lease.add_device_reservation(
    amount=3, machine_type=machine_name, device_name=device_name
)
container_lease.submit()
print("Done!")

This code creates a lease for 3 devices of the same type (raspberrypi4-64) and reserves them for 4 hours. You can adjust the machine_name, device_name, and lease_name variables as needed for your specific use case.

Note: Make sure to replace the device_name variable with the actual name of the device you want to reserve. You can find the list of available devices on the CHI@Edge testbed by using the Hardware Discovery page or the chi command-line tool.

Also, be aware that the add_device_reservation method may fail if there are not enough available devices of the specified type. You can check the availability of devices using the Resource Calendars page or the chi command-line tool before submitting the lease request.

Further Reading
DocsGui
BlogChi In A Box Update
BlogExperiment Patterns Making Complex Experiments Easy
BlogPackaging Your Experiments On Chameleon With Python Chi 10
BlogConducting Research On The Edge Chiedge
DocsGetting Started |  | 1 | amount=3 with single device_name='iot-rpi4-picam3' will fail — trap not caught. |
| P04 | Reservation | S2 · GPT (blind) | I cannot directly access or operate the CHI@Edge portal to create a lease.

To reserve 3 Raspberry Pis of the same hardware type in a single lease, you would typically:

Log in to the CHI/CHI@Edge dashboard.
Create a new lease.
Select a site that has Raspberry Pi nodes available.
Filter the node list by Raspberry Pi model (for example, Raspberry Pi 4).
Request 3 nodes of the same type.
Set the lease start time and duration.
Submit the lease request.

If you are using the CHI API, CLI, or Jupyter notebooks, provide the method you are using and I can give the exact commands. |  | 0 | Refuses; portal steps only; no code. |
| P04 | Reservation | S2 · GPT (artifact) | To reserve 3 Raspberry Pis of the same type in a single CHI@Edge lease, use one lease and add a device reservation with amount=3 for the desired machine type. The artifact shows leases are created with lease.Lease(...) and reservations are added via add_device_reservation(...).

Example:

from chi import lease
import chi

chi.context.use_site("CHI@Edge")
chi.context.choose_project()

machine_name = "raspberrypi4-64"

container_lease = lease.Lease(
    name="three-rpis",
    duration=lease.timedelta(hours=4)
)

container_lease.add_device_reservation(
    amount=3,
    machine_type=machine_name
)

container_lease.submit()

print("Lease created.")

The Raspberry Pi type used throughout the artifact is raspberrypi4-64.

If you need three specific Raspberry Pis, you would typically create separate reservations naming each device, whereas the example above requests any three available nodes of type raspberrypi4-64. The artifact's single-device example uses amount=1, machine_type=machine_name, and device_name=device_name. |  | 2 | Perfect; correctly omits device_name and explains why. |
| P04 | Reservation | S3 · Claude (blind) | There's no dedicated Chameleon Cloud / CHI@Edge MCP connector available. I can walk you through how to do this directly using the Chameleon Cloud portal or the Python chi SDK.

Here's how to reserve 3 Raspberry Pis of the same type in a single lease on CHI@Edge:
Option 1: Via the Chameleon Portal (GUI)

Go to chi.edge.chameleoncloud.org and log in.
Navigate to Reservations → Leases → Create Lease.
Give your lease a name, set your start/end dates.
Under Resources, click Add Resource → Physical Host.
Set:

Resource Type: node
Node Type: choose the Raspberry Pi model (e.g., rpi4, rpi3b+, etc.) — you can browse available types at the Hardware Discovery page.
Min/Max Count: 3 for both (to guarantee exactly 3).


Submit the lease.


Option 2: Via the Python chi SDK
pythonimport chi
from chi import lease

chi.use_site("CHI@Edge")
chi.set("project_name", "YOUR_PROJECT_NAME")

# Find the exact node type name first
# You can list available node types with:
# chi.hardware.list_nodes()  # look for 'node_type' values like 'raspberrypi4-64'

reservations = []
lease.add_node_reservation(
    reservations,
    count=3,
    node_type="raspberrypi4-64",   # <-- replace with the exact type from hardware discovery
)

my_lease = lease.create_lease(
    "my-rpi-lease",
    reservations=reservations,
    start_date="2026-06-23T09:00",   # UTC, or use "now" to start immediately
    end_date="2026-06-24T09:00",
)

print(my_lease["id"])

Finding Available Raspberry Pi Node Types
To see what Pi types are available on CHI@Edge:
pythonimport chi
chi.use_site("CHI@Edge")

nodes = chi.hardware.get_nodes()
rpi_nodes = [n for n in nodes if "raspberry" in n.get("node_type", "").lower()]
for n in rpi_nodes:
    print(n["node_type"], "-", n.get("architecture", {}).get("platform_type"))
Or browse the CHI@Edge hardware catalog and filter by "Edge".

Key tip: Set min_count == max_count == 3 (or both to 3 in the SDK) to ensure the lease is only granted when all 3 nodes of the same type are available. If you use min=1, max=3, you might get fewer than 3.
Would you like help with anything else, like launching instances on those nodes after the lease is active? |  | 0 | Bare-metal trap: add_node_reservation despite correct machine name. |
| P04 | Reservation | S3 · Claude (artifact) | Based on the artifact, you just need to set amount=3 in add_device_reservation. Since you want any 3 of the same type (not specific named devices), you can omit device_name and let Blazar pick them.
pythonimport chi
from chi import lease
import os

chi.context.use_site("CHI@Edge")
chi.context.choose_project()  # comment out if running outside JupyterHub

machine_name = "raspberrypi4-64"

username = os.environ.get("USER")
lease_name = f"{username}-rpi4-3x"

container_lease = lease.Lease(
    name=lease_name,
    duration=lease.timedelta(hours=4)
)

container_lease.add_device_reservation(
    amount=3,
    machine_type=machine_name
    # No device_name — lets Blazar pick any 3 available raspberrypi4-64 nodes
)

container_lease.submit()
print("Done!")
Key changes from the artifact's single-device pattern:
Artifact (1 device)This request (3 devices)amount13device_name"iot-rpi4-picam3" (specific node)omitted (any available)machine_type"raspberrypi4-64""raspberrypi4-64" (same)
A few notes:

If you do need specific named nodes, pass a list: you'll need to call add_device_reservation three times (once per device name), since each call targets one named device.
After the lease is active, container_lease.device_reservations will be a list of 3 reservation objects. You'd index them ([0], [1], [2]) when launching containers against each node.
amount=3 will fail at submit time if fewer than 3 raspberrypi4-64 nodes are free — check availability in the CHI@Edge hardware browser first. |  | 2 | Perfect; clear diff table vs artifact; correct API. |
| P05 | Container | S1 · Chatbot (blind) | To launch a basic Ubuntu container on a reserved Pi on CHI@Edge, follow these steps:

Reserve a Pi: First, ensure you have a Pi reserved on CHI@Edge. This involves using the CHI@Edge interface to select and reserve a Raspberry Pi device.

Prepare the Environment: Make sure you have the necessary tools and credentials to interact with CHI@Edge. This typically involves having an account, appropriate permissions, and possibly specific software or libraries installed on your local machine.

Choose an Ubuntu Image: Select a suitable Ubuntu image that is compatible with the Raspberry Pi architecture (e.g., ARM64). CHI@Edge might provide pre-configured images or you might need to specify one from a container registry like Docker Hub.

Launch the Container: Use the CHI@Edge interface or command-line tools to launch a container from the chosen Ubuntu image on your reserved Pi. This step may involve specifying the image name, any necessary environment variables, and ensuring the container is configured to run with appropriate permissions and resources.

Verify the Container: After launching, verify that the Ubuntu container is running successfully on the Pi. This could involve checking the container's status through the CHI@Edge interface, executing commands inside the container, or accessing services exposed by the container.

For detailed commands and specific configurations, refer to the official CHI@Edge and CHI documentation, as the exact steps can vary based on the version of the platform and the tools you are using. |  | 0 | Vague prose; no code; references docs. |
| P05 | Container | S1 · Chatbot (artifact) | To launch a basic Ubuntu container on a reserved Pi on CHI@Edge, you would need to follow these steps based on the provided context:

Choose the Site and Project: Start by selecting the CHI@Edge site and your project using the context.choose_site and context.choose_project methods from the python-chi library.

Find Available Devices: Use the hardware.get_devices method to find available Raspberry Pi devices. You would filter these by device_type="raspberrypi4-64" and then further filter the results to only include devices whose names start with "iot-rpi4-picam".

Create a Lease: Create a lease for the desired device using the lease.Lease class. Specify the lease duration, typically 3 hours in the examples provided.

Launch a Container: With the lease in place, launch a container on the reserved device. You would use the container.Container class, specifying the image reference for a basic Ubuntu image (not explicitly provided in the context but implied as necessary for the task), and ensure that the device_profiles include any necessary profiles for the device, such as "pi_libcamera" for camera-enabled devices.

Execute Commands in the Container: Once the container is running, you can execute commands inside it using the my_container.execute method. This could include commands to verify the container's environment, install additional packages, or run applications.

Cleanup: After completing your work, remember to delete the container and the lease to free up resources.

Here's a simplified example based on the provided context:

from chi import context, hardware, lease, container
from datetime import timedelta

# Choose site and project
context.choose_site(default="CHI@Edge")
context.choose_project()

# Find available devices
device_type = "raspberrypi4-64"
available_devices = hardware.get_devices(filter_reserved=True, device_type=device_type)
picamera_devs = [d for d in available_devices if d.device_name.startswith("iot-rpi4-picam")]

# Create a lease
my_lease = lease.Lease("ubuntu-lease", duration=timedelta(hours=3))
my_lease.add_device_reservation(devices=[picamera_devs[0]])
my_lease.submit(idempotent=True)

# Launch a container
# Note: The exact Ubuntu image reference is not provided in the context.
# Replace "ubuntu_image_ref" with the actual reference to a basic Ubuntu image.
ubuntu_image_ref = "replace_with_actual_ubuntu_image_ref"
my_container = container.Container(
    "ubuntu-test",
    image_ref=ubuntu_image_ref,
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    # Adjust device_profiles as necessary for your use case
    device_profiles=["pi_libcamera"],
)
my_container.submit()

# Execute commands in the container (example)
cmd = "echo 'Hello from Ubuntu container!'"
result, code = my_container.execute(cmd)
print(result)

# Cleanup
my_container.delete()
my_lease.delete()

Please note, the actual Ubuntu image reference (ubuntu_image_ref) is not provided in the context and would need to be replaced with a valid reference to a basic Ubuntu image compatible with CHI@Edge and the Raspberry Pi 4. Additionally, the device_profiles might need adjustment based on the specific requirements of your container and the device capabilities.

Further Reading
DocsGui
BlogChi In A Box Update
BlogCloud Wrangling Chameleons Python Library
BlogThe Hitchhikers Guide To Chameleon Documentation Finding Answers Fast
BlogTrovi Google Drive Chameleon Experiments
BlogConducting Research On The Edge Chiedge |  | 1 | Right API skeleton but leaves image as placeholder; adds unneeded pi_libcamera. |
| P05 | Container | S2 · GPT (blind) | I cannot directly access or control a CHI@Edge reservation, but if you already have a reserved Raspberry Pi node, you can launch a basic Ubuntu container from the node's shell.

1. SSH to the reserved Pi
ssh cc@<node-ip>

or, if using the CHI lease tools:

ssh cc@<reserved-node-name>
2. Verify Docker is available
docker --version

If Docker is not running:

sudo systemctl start docker
3. Pull an Ubuntu image
docker pull ubuntu:22.04
4. Launch the container

Interactive shell:

docker run -it --name ubuntu-test ubuntu:22.04 bash

Detached container:

docker run -d --name ubuntu-test ubuntu:22.04 sleep infinity
5. Access a running detached container
docker exec -it ubuntu-test bash
6. Confirm Ubuntu is running

Inside the container:

cat /etc/os-release

You should see output identifying Ubuntu 22.04.

If you're using the CHI@Edge dashboard and have details about the reserved Pi (node name, reservation type, Kubernetes vs. bare-metal access), provide them and I can give the exact commands for that setup. |  | 0 | Uses docker CLI not python-chi; wrong tool entirely. |
| P05 | Container | S2 · GPT (artifact) | Based on the CHI@Edge artifact, a basic Ubuntu container can be launched on a reserved Raspberry Pi 4 by following the same lease-and-container pattern used for the camera example, but without the camera-specific image and device profile.

1. Select CHI@Edge and a project
from chi import context

context.choose_site(default="CHI@Edge")
context.choose_project()
2. Find and reserve a Raspberry Pi

The artifact uses Raspberry Pi 4 devices with:

device_type = "raspberrypi4-64"

Reserve one:

from chi import hardware, lease
from datetime import timedelta

available_devices = hardware.get_devices(
    filter_reserved=True,
    device_type="raspberrypi4-64"
)

rpi = available_devices[0]

my_lease = lease.Lease(
    "ubuntu-rpi-lease",
    duration=timedelta(hours=3)
)

my_lease.add_device_reservation(devices=[rpi])
my_lease.submit(idempotent=True)
3. Launch an Ubuntu container

Using the same container.Container API pattern from the artifact:

from chi import container

my_container = container.Container(
    "ubuntu-rpi-container",
    image_ref="ubuntu:24.04",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"]
)

my_container.submit()
4. Verify the container

Execute a command inside the running container:

result, code = my_container.execute("uname -a")
print(result)

Or:

result, code = my_container.execute("cat /etc/os-release")
print(result)
5. Cleanup
my_container.delete()
my_lease.delete()
Notes

The camera artifact's container required:

device_profiles=["pi_libcamera"]
image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest"

Those are only needed when accessing the Pi Camera Module 3. For a basic Ubuntu container on a reserved Pi, they can be omitted. The critical pieces are:

context.choose_site(default="CHI@Edge")
Reserving a raspberrypi4-64 device with lease.Lease
Passing the reservation ID into container.Container
Using a long-running command such as ["sleep", "infinity"] so the container remains available for interactive execution. |  | 2 | Correct API; properly drops camera profile; clean. |
| P05 | Container | S3 · Claude (blind) | Here's how to launch a basic Ubuntu container on a reserved Raspberry Pi on CHI@Edge using the Chameleon Python client (chi).
Prerequisites

An active CHI@Edge account at chi.edge.chameleoncloud.org
A lease with a Pi node reservation already created
Your project credentials / clouds.yaml or application credentials configured


Step 1 — Install the Chameleon client
bashpip install chi

Step 2 — Authenticate
In a Jupyter notebook (e.g., on jupyter.chameleoncloud.org) or locally:
pythonimport chi
import chi.container

# Set your project
chi.set("project_name", "CHI-XXXXXX")   # replace with your project ID
chi.set("region_name", "CHI@Edge")       # or the correct site alias
chi.use_site("chi@edge")

Step 3 — Find your reservation
pythonfrom chi.lease import get_lease, get_node_reservation

lease = get_lease("my-pi-lease")          # replace with your lease name
reservation_id = get_node_reservation(lease["id"])
print("Reservation ID:", reservation_id)

Step 4 — Launch the Ubuntu container
pythoncontainer = chi.container.create_container(
    name="ubuntu-pi-test",
    image="ubuntu:22.04",
    reservation_id=reservation_id,
    command=["sleep", "infinity"],        # keep container alive
)

print("Container ID:", container["uuid"])
print("Status:", container["status"])

sleep infinity keeps the container running so you can exec into it. Swap it for your actual workload command when ready.


Step 5 — Wait for it to be running
pythonchi.container.wait_for_active(container["uuid"])
print("Container is active!")

Step 6 — Open a shell inside the container
python# Execute a command
chi.container.execute(container["uuid"], "uname -a")
Or via the Horizon GUI → Containers → your container → Execute Command.

Step 7 — Clean up when done
pythonchi.container.destroy_container(container["uuid"])

Key notes
ThingDetailImageAny Docker Hub image works; arm64 images are required for Pi hardwareubuntu:22.04Has an official linux/arm64 variant — pulls automaticallyNetworkingContainers get a floating IP if you attach one via chi.container.associate_floating_ip()Lease requiredContainer creation will fail without a valid, active node reservation
If you haven't created a lease yet, let me know and I can walk you through that step first. |  | 1 | Functional API mostly works; invents chi.set('region_name'); platform_version=2 correct. |
| P05 | Container | S3 · Claude (artifact) | Here's how to launch a basic Ubuntu container on a reserved Raspberry Pi on CHI@Edge, following the same python-chi patterns from the artifact:
1. Set up context
pythonfrom chi import context

context.choose_site(default="CHI@Edge")
context.choose_project()
2. Find an available Pi
pythonfrom chi import hardware

available_devices = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
print([d.device_name for d in available_devices])
filter_reserved=True returns only devices not currently reserved, so any device from this list is fair game.
3. Create and submit a lease
pythonfrom chi import lease
from datetime import timedelta

my_lease = lease.Lease("rpi4-ubuntu-lease", duration=timedelta(hours=3))
my_lease.add_device_reservation(devices=[available_devices[0]])
my_lease.submit(idempotent=True)
4. Launch a basic Ubuntu container
pythonfrom chi import container

my_container = container.Container(
    "rpi4-ubuntu-test-01",
    image_ref="ubuntu:24.04",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],   # keeps the container alive for interactive use
)
my_container.submit()
A few notes on what changed vs. the camera artifact:

image_ref — swap in any standard Docker Hub image like ubuntu:24.04 (or ubuntu:22.04). The camera artifact used a custom ghcr.io/chameleoncloud/edge-picamera-image:latest because it needed libcamera/rpicam pre-installed.
device_profiles — omitted entirely. ["pi_libcamera"] was only needed to expose /dev camera nodes; a plain Ubuntu container doesn't need it.
command=["sleep", "infinity"] — same pattern as the artifact, keeps the container running so you can execute() commands interactively.

5. Run commands interactively
pythonresult, code = my_container.execute("uname -a")
print(result)

result, code = my_container.execute("apt-get update && apt-get install -y python3")
print(result)
6. Cleanup
pythonmy_container.delete()
my_lease.delete()

Quick reference — what maps to what:
Artifact (camera)Basic Ubuntughcr.io/chameleoncloud/edge-picamera-image:latestubuntu:24.04device_profiles=["pi_libcamera"](omit)iot-rpi4-picam* filterany raspberrypi4-64 device |  | 2 | Correct; explicit diff vs artifact; clean. |
| P06 | Container | S1 · Chatbot (blind) | To keep a container running on CHI@Edge so you can exec into it, you need to ensure that the container has a long-running command or process. By default, if the command or process specified in the container's entrypoint or command completes, the container will exit.

Here are steps to make your container stay running:

Check the Container's Command: Verify the command that is being executed when your container starts. If this command completes quickly, the container will exit. You can check this by looking at the container's configuration or the Dockerfile used to create the image.

Use a Long-Running Command: Modify the command that runs when your container starts to something that keeps running indefinitely. A common approach is to use a command like tail -f /dev/null at the end of your command sequence. This command will keep the container running without doing any actual work.

Modify the Dockerfile or Container Configuration: If you have access to the Dockerfile, you can modify the CMD instruction to include a long-running command. Alternatively, if you're using a container configuration file (like a YAML file for a pod in Kubernetes), you can modify the command field there.

Use an Interactive Shell: Another approach is to run the container with an interactive shell. You can do this by overriding the default command when you run the container. For example, if your container normally runs a command like myapp, you could run it with bash or sh instead: docker run -it myimage /bin/bash. This will give you an interactive shell inside the container, keeping it running until you exit the shell.

Exec into the Container: Once your container is running and staying up, you can exec into it using docker exec. For example: docker exec -it mycontainer /bin/bash. This will open a new interactive shell inside the running container.

Remember, the key is to ensure there's a process running inside the container that prevents it from exiting immediately. If you're working within a specific framework or toolset on CHI@Edge, consult the relevant documentation for any specific recommendations or requirements for keeping containers running.


 |  | 1 | Generic Docker advice (tail -f /dev/null); not python-chi specific; verbose. |
| P06 | Container | S1 · Chatbot (artifact) | To keep your container running on CHI@Edge so you can exec into it, you should use a command that keeps the container active. According to the provided artifact, this can be achieved by setting the command parameter of the container.Container object to ["sleep", "infinity"]. This command keeps the container running indefinitely, allowing you to exec into it.

Here's how you can do it:

my_container = container.Container(
    "your-container-name",
    image_ref="your-image-reference",
    exposed_ports=[],
    reservation_id="your-reservation-id",
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)
my_container.submit()

By using ["sleep", "infinity"] as the command, your container will stay running, enabling you to execute commands inside it.

Further Reading
DocsGui
BlogChi In A Box Update
BlogCloud Wrangling Chameleons Python Library
BlogThe Hitchhikers Guide To Chameleon Documentation Finding Answers Fast
BlogTrovi Google Drive Chameleon Experiments
BlogConducting Research On The Edge Chiedge

 |  | 2 | Direct correct answer; carries unneeded pi_libcamera. |
| P06 | Container | S2 · GPT (blind) | A container exits when its PID 1 process exits. To keep it alive long enough to exec into it, run a long-lived foreground process as the container command.

Common options:

sleep infinity

or

tail -f /dev/null

or

while true; do sleep 3600; done

Examples:

docker run -d --name debug-container myimage sleep infinity

In a Dockerfile:

CMD ["sleep", "infinity"]

For Kubernetes:

containers:
- name: app
  image: myimage
  command: ["sleep"]
  args: ["infinity"]

For CHI@Edge specifically, override the container's startup command to one of the above and redeploy. Once the container is running:

docker exec -it <container-id> /bin/sh

or

kubectl exec -it <pod-name> -- /bin/sh

If you're using CHI@Edge with a specific orchestration method (container reservation, K8s manifest, Horizon dashboard, etc.), paste the deployment spec and I can show the exact change. |  | 1 | Correct concept (sleep infinity) but Docker/K8s syntax; not python-chi. |
| P06 | Container | S2 · GPT (artifact) | Based on the CHI@Edge artifact you provided, the intended pattern is to start a long-lived process as the container's main command:

my_container = container.Container(
    "rpi4-camera-test-01",
    image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)
my_container.submit()

The key part is:

command=["sleep", "infinity"]

If your container exits immediately, common causes are:

1. No long-running command specified

For example, this will exit as soon as the shell finishes:

command=["bash"]

or

command=["python3", "camera_test.py"]

Use:

command=["sleep", "infinity"]

instead.

2. Overriding the image's default command with a short-lived process

The reference image (ghcr.io/chameleoncloud/edge-picamera-image:latest) is built with:

CMD ["sleep", "infinity"]

If you supply your own command that terminates, the container will stop.

3. The startup command is failing

Check container status and logs. A typo such as:

command=["sleep", "infinity"]   # misspelled

or a missing executable will cause immediate exit.

Recommended workflow on CHI@Edge

Start the container exactly as in the artifact:

my_container = container.Container(
    "rpi4-camera-test-01",
    image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)

my_container.submit()

Then run commands interactively:

result, code = my_container.execute(
    "rpicam-hello --nopreview --list-cameras"
)

result, code = my_container.execute(
    "rpicam-still --nopreview --output /app/test1.png --width 1920 --height 1080"
)

rather than making the camera command the container's main process.

If you're already using command=["sleep", "infinity"] and it still exits, share the exact Container(...) definition and any status/log output, because that would indicate a startup failure rather than normal container behavior. |  | 2 | Correct + helpful diagnostic notes on causes. |
| P06 | Container | S3 · Claude (blind) | The classic fix is to give the container an indefinitely-blocking entrypoint. Here are your options, from simplest to most flexible:

Option 1 — sleep infinity (simplest)
bashdocker run -d --name my-container <image> sleep infinity
If the image has no shell, use the exec form:
bashdocker run -d --name my-container --entrypoint sleep <image> infinity
Then exec in:
bashdocker exec -it my-container /bin/sh   # or /bin/bash

Option 2 — Override entrypoint at run time
If you need the original entrypoint to not run (e.g., it crashes on missing config):
bashdocker run -d --name my-container --entrypoint tail <image> -f /dev/null
tail -f /dev/null blocks forever and is available on virtually every image.

Option 3 — Fix the image itself
In your Dockerfile, set a default command that blocks:
dockerfileCMD ["sleep", "infinity"]
or keep your real entrypoint but make it run in the background and then sleep:
dockerfileCMD ["/bin/sh", "-c", "your-start-script.sh & sleep infinity"]

Option 4 — docker run -it with a TTY (interactive debugging)
If you just need a one-off interactive session without a running daemon:
bashdocker run -it --rm <image> /bin/sh
This keeps the container alive as long as your terminal session is open.

CHI@Edge-specific notes
If you're using the Chameleon portal / chi CLI to launch containers, the pattern is the same but you pass the command through the lease/container spec:
bashchi container create \
  --name my-container \
  --image <image> \
  --command '["sleep", "infinity"]'
Then:
bashchi container exec -it my-container /bin/sh

Recommended default: sleep infinity — it's the most portable, uses zero CPU, and makes intent obvious. Use tail -f /dev/null as a fallback if sleep isn't in the image. |  | 1 | Generic Docker; mentions a 'chi container create' CLI that doesn't exist. |
| P06 | Container | S3 · Claude (artifact) | Pass command=["sleep", "infinity"] when creating your container:
pythonmy_container = container.Container(
    "rpi4-camera-test-01",
    image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)
my_container.submit()
The image's default CMD is also ["sleep", "infinity"], but if you're overriding the command anywhere (or using a different image), that's what causes the immediate exit — the container has nothing to do and stops. Passing it explicitly ensures it stays up indefinitely, and you can then use my_container.execute(cmd) to run commands inside it. |  | 2 | Direct correct; notes the image's default CMD. |
| P07 | Container | S1 · Chatbot (blind) | To expose port 8080 on your CHI@edge container and give it a public IP, you will need to follow these steps:

Allocate a Floating IP address: Since CHI@edge instances are assigned a fixed IP address that can be used for local connectivity as well as NAT access to the public Internet, you need to allocate a Floating IP address to make your instance publicly accessible. The getting-started guide shows how to allocate a Floating IP address to your nodes.

Assign the Floating IP to your instance: Once you have allocated a Floating IP address, you need to assign it to your CHI@edge instance. This will give your instance a publicly accessible IPv4 address.

Configure port forwarding: To expose port 8080 on your CHI@edge container, you need to configure port forwarding. This step is not explicitly mentioned in the provided primary documentation, so you may need to refer to additional resources or the getting-started guide for specific instructions on how to do this.

Ensure security best practices: As mentioned in the supplementary context, it's essential to use public IP addresses sparingly and consider security best practices, such as using a bastion host to limit the attack surface. However, this is not directly related to exposing a port and assigning a public IP.

Please note that the primary documentation does not provide detailed instructions on configuring port forwarding, so you may need to consult additional resources or the getting-started guide for more information.

Further Reading
BlogExperiment Pattern Bastion Host
DocsNetworks Basic

 |  | 0 | Vague portal-level guidance; no code; misses both API calls. |
| P07 | Container | S1 · Chatbot (artifact) | To expose port 8080 on your CHI@Edge container and give it a public IP, you can follow these steps based on the provided python-chi code:

Create a lease: First, ensure you have a lease for a device on CHI@Edge. This involves selecting the site, setting up your project, and creating a lease for the desired device (e.g., raspberrypi4-64).

Create a container: With the lease active, create a container using the container.create_container method. When creating the container, specify the image you wish to use, and make sure to expose port 8080 by including it in the exposed_ports list.

Associate a floating IP: After the container is created, you can associate a floating IP with it using the chi.container.associate_floating_ip method. This will give your container a public IP address that you can use to access it from outside the CHI@Edge network.

Here's a simplified example based on the provided code:

import chi
from chi import container
from chi import lease

# Select the CHI@Edge site
chi.use_site("CHI@Edge")

# Set your project name
chi.set("project_name", "YourProjectName")

# Define your machine name and lease duration
machine_name = "raspberrypi4-64"
start, end = lease.lease_duration(days=1)

# Create a lease
lease_name = f"your-lease-{machine_name}-{start}"
reservations = []
lease.add_device_reservation(reservations, count=1, machine_name=machine_name)
container_lease = lease.create_lease(lease_name, reservations)
lease_id = container_lease["id"]
lease.wait_for_active(lease_id)

# Create a container with port 8080 exposed
container_name = f"your-container-{machine_name}"
image = "your-image-name:latest"  # Replace with your actual image name
my_container = container.create_container(
    container_name,
    image=image,
    workdir="/home",
    exposed_ports=[22, 8080],  # Expose both SSH and your desired port
    reservation_id=lease.get_device_reservation(lease_id),
    platform_version=2,
)

# Associate a floating IP with the container
ip_address = chi.container.associate_floating_ip(my_container.uuid)

print(f"Container IP: {ip_address}")
print("You can now access your container on port 8080 using the floating IP.")

Replace "YourProjectName", "your-lease", "your-container", and "your-image-name:latest" with appropriate values for your project and container. This example assumes you have already set up your environment and have the necessary credentials to use the CHI@Edge testbed.

Further Reading
DocsGui
BlogChi In A Box Update
DocsFederation
DocsGetting Started
BlogSeamless Ssh Container Access With Chiedge
BlogBack To School With Chameleon

 |  | 2 | Correct: integer ports + associate_floating_ip; uses functional style from artifact. |
| P07 | Container | S2 · GPT (blind) | I can’t perform actions on your infrastructure directly.

If CHI@edge is a Kubernetes workload, Docker container, VM, or a specific edge platform, provide:

Platform/service name (CHI@edge, K3s, Kubernetes, Docker, etc.)
Current deployment manifest, compose file, or container configuration
Whether you want:
Port 8080 exposed internally only
Port 8080 exposed via a public LoadBalancer
Port 8080 exposed through an Ingress/reverse proxy
A dedicated public IP assigned

Examples:

Docker

docker run -d \
  -p 8080:8080 \
  your-image

Kubernetes Service with public IP

apiVersion: v1
kind: Service
metadata:
  name: app
spec:
  type: LoadBalancer
  selector:
    app: app
  ports:
    - port: 8080
      targetPort: 8080

Kubernetes Ingress

apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app
spec:
  rules:
  - host: app.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: app
            port:
              number: 8080

Share the deployment details and I can give the exact configuration needed. |  | 0 | Refuses + generic Docker/K8s/Ingress; misses python-chi entirely. |
| P07 | Container | S2 · GPT (artifact) | Based on the artifact, you expose a container port by changing the exposed_ports argument in container.create_container(), then associate a floating IP with the container using chi.container.associate_floating_ip().

Create the container with port 8080 exposed
my_container = container.create_container(
    container_name,
    image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
    workdir="/home",
    exposed_ports=[8080],
    reservation_id=lease.get_device_reservation(lease_id),
    platform_version=2,
)

If you want both SSH and your application on port 8080:

my_container = container.create_container(
    container_name,
    image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
    workdir="/home",
    exposed_ports=[22, 8080],
    reservation_id=lease.get_device_reservation(lease_id),
    platform_version=2,
)

The rest of the lease setup remains exactly as shown in the artifact:

chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")

machine_name = "raspberrypi4-64"

start, end = lease.lease_duration(days=1)

reservations = []
lease.add_device_reservation(
    reservations,
    count=2,
    machine_name=machine_name,
)

container_lease = lease.create_lease(lease_name, reservations)
lease.wait_for_active(container_lease["id"])
Associate a public IP

After the container is running:

ip_address = chi.container.associate_floating_ip(my_container.uuid)

print(f"Public IP: {ip_address}")
Access the service

If your application listens on 0.0.0.0:8080 inside the container:

http://<public-ip>:8080

For example:

print(f"http://{ip_address}:8080")

The authoritative CHI@Edge artifact uses:

Site: CHI@Edge
Machine type: raspberrypi4-64
Reservation count: 2
Image: ghcr.io/chameleoncloud/edge_ssh_image:latest
Public IP attachment: chi.container.associate_floating_ip(my_container.uuid)

The only change needed to expose your web service is replacing exposed_ports=[22] with exposed_ports=[8080] (or [22, 8080] if SSH access is still desired). |  | 2 | Correct; directly applies artifact pattern. |
| P07 | Container | S3 · Claude (blind) | I don't have tools to connect to or manage CHI@edge (Chameleon Cloud's edge infrastructure) directly. You'll need to do this through their platform, but here's how:
1. Expose port 8080 in your container
When creating/updating your container via the CHI@edge CLI or Zun API, add a port mapping:
bashopenstack container create \
  --name my-container \
  --image <your-image> \
  --exposed-port 8080/tcp \
  ...
Or if using the Python SDK:
pythonconn.container.create_container(
    name="my-container",
    image="your-image",
    ports=["8080/tcp"]
)
2. Assign a Floating (Public) IP
bash# Allocate a floating IP from the public pool
openstack floating ip create public

# Associate it with your container
openstack container add floating ip <container-name> <floating-ip>
3. Update the Security Group
Make sure the security group attached to your container allows inbound TCP on 8080:
bashopenstack security group rule create \
  --protocol tcp \
  --dst-port 8080 \
  --remote-ip 0.0.0.0/0 \
  <your-security-group>
Helpful resources:

CHI@edge docs: chameleoncloud.org/experiment/chiedge
Chameleon CLI setup: pip install python-openstackclient
You'll need your clouds.yaml or openrc credentials from the Chameleon portal

Would you like help with any specific part of this, like writing a script to automate the setup? |  | 0 | Wrong port format ('8080/tcp' string); invents openstack CLI. |
| P07 | Container | S3 · Claude (artifact) | Based on the artifact, you just need two changes from the SSH example: swap port 22 for 8080 in exposed_ports, then call associate_floating_ip as usual. Here's the relevant code:
pythonimport chi
from chi import container, lease

chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")

# --- Lease ---
machine_name = "raspberrypi4-64"
start, end = lease.lease_duration(days=1)
lease_name = f"myapp-{machine_name}-{start}"

reservations = []
lease.add_device_reservation(reservations, count=2, machine_name=machine_name)
container_lease = lease.create_lease(lease_name, reservations)
lease_id = container_lease["id"]

print(f"Waiting for lease {lease_name} ({lease_id}) to become active…")
lease.wait_for_active(lease_id)
print("Lease active!")

# --- Container ---
container_name = f"myapp-{machine_name}-8080".replace("_", "-")

my_container = container.create_container(
    container_name,
    image="ghcr.io/chameleoncloud/edge_ssh_image:latest",  # swap for your own image
    workdir="/home",
    exposed_ports=[8080],          # ← changed from [22] to [8080]
    reservation_id=lease.get_device_reservation(lease_id),
    platform_version=2,
)
print(f"Container created: {container_name}")

# --- Public IP ---
ip_address = chi.container.associate_floating_ip(my_container.uuid)
print(f"Reachable at: http://{ip_address}:8080")
What changed vs. the SSH tutorial:
SSH tutorialYour versionexposed_ports[22][8080]Key upload / authorized_keys steps✓ includedomit (not needed unless you also want SSH)associate_floating_ip✓✓ same call
A few things to keep in mind:

Container image — swap ghcr.io/chameleoncloud/edge_ssh_image:latest for whichever image actually listens on 8080 (e.g. a custom web server image). The SSH image above only runs sshd, so nothing will be listening on 8080 unless you change CMD.
Security group / firewall — after associating the floating IP, verify that CHI@Edge's OpenStack security group allows inbound TCP 8080. You can do this from the CHI@Edge Horizon dashboard under Network → Security Groups, or with the OpenStack CLI.
Floating IP hang — as noted in the artifact, if connecting hangs, release the floating IP via the CHI@Edge OpenStack dashboard and re-run associate_floating_ip.
Cleanup — when done, call chi.container.destroy_container(my_container.uuid) to free the device.
 |  | 2 | Correct + practical notes on listening, security group, hang fix. |
| P08 | Container | S1 · Chatbot (blind) | To run 'ls /app' inside the running container in CHI@Edge and capture the output, you can use SSH to access the container. Once you have SSH access to the container, you can run the command 'ls /app' and capture the output. The exact steps to establish SSH access are not provided in the given context, but it is mentioned that SSH access is available as an alternative to the web console in the CHI@Edge dashboard.

After establishing SSH access, you can run the command as follows:

ssh <container-ssh-access> "ls /app"

This will execute the 'ls /app' command inside the container and print the output to your local terminal. Replace <container-ssh-access> with the actual SSH access details provided by CHI@Edge for your container.

Further Reading
BlogSeamless Ssh Container Access With Chiedge

 |  | 0 | Falls back to SSH; misses the execute() API. |
| P08 | Container | S1 · Chatbot (artifact) | To run 'ls /app' inside the running container in CHI@Edge and capture the output, you can use the execute method of the container object in python-chi.

Here's a step-by-step example based on the provided artifact:

First, ensure you have a running container. If you don't, you'll need to create one using the container.Container class, similar to how my_container is created in the artifact.

Once you have a container, you can execute a command inside it using the execute method. For your case, the command to list the contents of the /app directory is ls /app.

Here's how you might do it in code, assuming my_container is your running container:

cmd = "ls /app"
result, code = my_container.execute(cmd)
print(result)

This will print the output of the ls /app command as it is executed inside the container. The result variable holds the output of the command, and code holds the return code of the command, which should be 0 if the command executed successfully.

Further Reading
DocsGui
BlogChi In A Box Update
BlogCloud Wrangling Chameleons Python Library
BlogThe Hitchhikers Guide To Chameleon Documentation Finding Answers Fast
BlogTrovi Google Drive Chameleon Experiments
BlogConducting Research On The Edge Chiedge

 |  | 2 | Correct + concise tuple unpacking. |
| P08 | Container | S2 · GPT (blind) | I cannot access or execute commands inside your CHI@Edge environment or any external running container.

If you have shell access to the container, run:

ls /app

Or, to capture the output:

ls /app > app_listing.txt
cat app_listing.txt

If you can provide:

the container name/ID,
the orchestration method (Docker, Kubernetes, CHI@Edge CLI, etc.), or
terminal access/output,

I can give the exact command sequence and help interpret the results. |  | 0 | Refuses; no API code; suggests shell only. |
| P08 | Container | S2 · GPT (artifact) | Command used in container:

cmd = "ls /app"
result, code = my_container.execute(cmd)
print(result)

Output:

camera_test.py
test1.png
test2.png
video1.mp4 |  | 2 | Most concise; correct; even mocks expected output. |
| P08 | Container | S3 · Claude (blind) | I don't have a direct connection to CHI@Edge or any Chameleon Cloud infrastructure. To run commands inside a container on CHI@Edge, you'd typically use one of these approaches:
Via SSH + Docker/Podman (most common):
bash# SSH into your CHI@Edge node first
ssh cc@<your-node-ip>

# Then exec into the running container
docker exec <container-name-or-id> ls /app
# or
podman exec <container-name-or-id> ls /app
Via the CHI@Edge Jupyter interface:

If you're using the Chameleon JupyterHub, you can run shell commands in a notebook cell:
pythonimport subprocess
result = subprocess.run(
    ["docker", "exec", "<container-id>", "ls", "/app"],
    capture_output=True, text=True
)
print(result.stdout)
Via the OpenStack CLI (if using Zun container service):
bashopenstack appcontainer exec <container-name> ls /app
What I'd need to help further:

I don't have credentials or network access to CHI@Edge infrastructure
There's no MCP connector available for Chameleon Cloud in my current toolset

To get this working yourself:

Log into chi.edge.chameleoncloud.org
SSH to your reserved node, or use the Jupyter environment
Run the docker exec / podman exec command above with your actual container name

If you paste the output here, I'm happy to help you interpret or work with the results! |  | 0 | docker exec / OpenStack CLI / subprocess — wrong API entirely. |
| P08 | Container | S3 · Claude (artifact) | Based on the artifact, here's exactly how to run ls /app inside the running container:
pythonresult, code = my_container.execute("ls /app")
print(result)
This assumes my_container is already submitted and running (i.e., you've already gone through the lease and container launch steps). The execute() method runs a shell command inside the container and returns a tuple of (stdout_output, exit_code).
Full context if you're running this fresh:
pythonfrom chi import context, hardware, lease, container
from datetime import timedelta

# 1. Site/project setup
context.choose_site(default="CHI@Edge")
context.choose_project()

# 2. Find a Pi Camera device
available_devices = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
picamera_devs = [d for d in available_devices if d.device_name.startswith("iot-rpi4-picam")]

# 3. Create and submit a lease
my_lease = lease.Lease("rpi4-camera-lease", duration=timedelta(hours=3))
my_lease.add_device_reservation(devices=[picamera_devs[0]])
my_lease.submit(idempotent=True)

# 4. Launch the container
my_container = container.Container(
    "rpi4-camera-test-01",
    image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)
my_container.submit()

# 5. Run ls /app
result, code = my_container.execute("ls /app")
print(result)
Expected output will list whatever is in /app inside the ghcr.io/chameleoncloud/edge-picamera-image:latest image. Based on the Dockerfile summary (WORKDIR /app), the directory starts empty — files like test1.png, test2.png, video1.mp4, and camera_test.py only appear there after you explicitly upload or capture them via subsequent execute() / upload() calls.
A couple of things to keep in mind:

If the container was already launched in a prior session, you can skip steps 1–4 and reconnect to the existing container by name/ID instead of re-creating it.
Exit code 0 in code confirms the command succeeded; a non-zero value means something went wrong (e.g., the container isn't running yet).
 |  | 2 | Correct API; bonus full context for fresh runs. |
| P09 | Container | S1 · Chatbot (blind) | To upload model.pt into the CHI@Edge container and download results.csv, you would typically use the CHI@Edge SDK. However, the provided supplementary context does not give specific steps or commands for uploading and downloading files. It mentions using a Jupyter Notebook to deploy new code to devices enrolled in CHI@Edge and the possibility of saving or uploading data to the cloud, but it does not provide detailed instructions for file transfer. Without access to the primary documentation, I don't know the exact steps or commands required for uploading model.pt and downloading results.csv using CHI@Edge.

Further Reading
BlogConducting Research On The Edge Chiedge

 |  | 0 | Honestly admits it doesn't know; no answer. |
| P09 | Container | S1 · Chatbot (artifact) | To upload model.pt into the CHI@Edge container and download results.csv back out, you would use the upload and download methods of the container object in the python-chi library.

Here's a step-by-step example based on the provided context:

Create a lease and launch a container: First, you need to create a lease for a device in CHI@Edge and launch a container on that device. This involves choosing a site, selecting a device, creating a lease, and then launching a container with the desired image and device profile.

Upload model.pt to the container: Once the container is running, you can upload model.pt to it using the upload method of the container object.

Execute any necessary commands in the container: If you need to run any commands inside the container to process model.pt and generate results.csv, you can use the execute method of the container object.

Download results.csv from the container: Finally, you can download results.csv from the container using the download method of the container object.

Here's some sample code based on the context provided:

from chi import context, lease, container
from datetime import timedelta

# Choose the site and project
context.choose_site(default="CHI@Edge")
context.choose_project()

# Create a lease for a device
my_lease = lease.Lease("my-lease", duration=timedelta(hours=3))
# Add a device reservation to the lease
# Assuming you have a device_type and device_name
my_lease.add_device_reservation(devices=[{"device_type": "raspberrypi4-64", "device_name": "iot-rpi4-picam"}])
my_lease.submit(idempotent=True)

# Launch a container
my_container = container.Container(
    "my-container",
    image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)
my_container.submit()

# Upload model.pt to the container
import os
cwd = os.getcwd()
my_container.upload(f"{cwd}/model.pt", "/app/")

# Execute any necessary commands in the container
# For example:
cmd = "python3 my_script.py"  # Assuming my_script.py processes model.pt and generates results.csv
result, code = my_container.execute(cmd)
print(result)

# Download results.csv from the container
my_container.download("/app/results.csv", ".")

# Clean up
my_container.delete()
my_lease.delete()

Note: This example assumes you have a script (my_script.py) inside the container that processes model.pt and generates results.csv. You need to adjust the cmd variable and the upload/download paths according to your specific requirements. Also, ensure that the device profile and image used support the necessary dependencies for your script to run.

Further Reading
DocsGui
BlogChi In A Box Update
BlogCloud Wrangling Chameleons Python Library
BlogThe Hitchhikers Guide To Chameleon Documentation Finding Answers Fast
BlogTrovi Google Drive Chameleon Experiments
BlogConducting Research On The Edge Chiedge

 |  | 2 | Correct upload/download; helpful full workflow context. |
| P09 | Container | S2 · GPT (blind) | model.pt isn’t available in the current workspace, so there’s nothing to upload into the CHI@Edge container yet.

What’s needed:

Provide the model.pt file (upload it here)
Confirm:
expected input data location (or format)
how inference should be run (script name, entrypoint, or command)
where results.csv should be written from (if not standard /output/results.csv)

Once the file is present, the workflow inside the container will be:

# inside CHI@Edge container
cp /mnt/data/model.pt /app/model.pt
python run_inference.py --model /app/model.pt --output /app/results.csv

Then:

pull file out of container:
cat /app/results.csv

or export it depending on the environment’s file bridge.

Upload model.pt and the run spec, and the exact container commands can be finalized. |  | 0 | Misreads request; thinks model.pt needs to be uploaded to the chat itself. |
| P09 | Container | S2 · GPT (artifact) | Use the existing CHI@Edge container handle (my_container) from the artifact workflow.

1. Upload model.pt into the container
my_container.upload("model.pt", "/app/model.pt")

Optional sanity check inside container:

result, code = my_container.execute("ls -lh /app")
print(result)
2. Run whatever produces results.csv (if required by your workflow)

If the model needs execution step, it would typically be something like:

# example placeholder – depends on your app
my_container.execute("python3 run_inference.py")
3. Download results.csv back to local
my_container.download("/app/results.csv", ".")

That pulls results.csv from the container filesystem into the current working directory on the Jupyter side. |  | 2 | Correct + concise. |
| P09 | Container | S3 · Claude (blind) | I don't have a direct integration or tool for CHI@Edge (Chameleon Cloud's edge infrastructure), so I can't connect to it on your behalf. Here's what you'd need to do this yourself, or how I can help:
If you have the Chameleon CLI set up in your environment, the typical workflow is:
bash# Upload model.pt to a container (using OpenStack Swift)
openstack object create <container-name> model.pt

# Or using the chi CLI / curl with a token
curl -X PUT -H "X-Auth-Token: <token>" \
  https://<chi-edge-endpoint>/v1/<account>/<container>/model.pt \
  --upload-file model.pt

# Download results.csv back out
openstack object save <container-name> results.csv
# or
curl -X GET -H "X-Auth-Token: <token>" \
  https://<chi-edge-endpoint>/v1/<account>/<container>/results.csv \
  -o results.csv
What I'd need to actually run this for you:

Your CHI@Edge endpoint URL and container name
An auth token (from openstack token issue or the Chameleon web dashboard)
The model.pt file uploaded here so I can place it in the container

Alternatively, if you're SSHing into a CHI@Edge node (not object storage), you'd use:
bashscp model.pt cc@<node-ip>:/path/to/destination/
scp cc@<node-ip>:/path/to/results.csv ./results.csv
Can you share more details — are you working with CHI@Edge object storage or a running edge node? And do you have credentials/tokens available? I can help write and run the exact commands once I know the setup. |  | 0 | OpenStack Swift / scp suggestions; wrong API. |
| P09 | Container | S3 · Claude (artifact) | Based on the artifact's python-chi patterns, here's how to upload model.pt into the container and download results.csv back out:
python# Upload model.pt into the running container
my_container.upload("model.pt", "/app/")

# ... run your inference workload ...
cmd = "python3 run_inference.py"   # or whatever produces results.csv
result, code = my_container.execute(cmd)
print(result)

# Download results.csv back to the local working directory
my_container.download("/app/results.csv", ".")
A few things worth knowing from the artifact:
container.upload(src, dst) — mirrors the pattern used for the helper script:
pythonmy_container.upload(f"{cwd}/camera_test.py", "/app/")
So my_container.upload("model.pt", "/app/") places the file at /app/model.pt inside the container. If model.pt isn't in your current working directory, use an absolute path or f"{os.getcwd()}/model.pt".
container.download(src, dst) — mirrors the still/video download pattern:
pythonmy_container.download("/app/test1.png", ".")
So my_container.download("/app/results.csv", ".") pulls the file into your local working directory.
Size caveat — the artifact notes:

container.download() is primarily meant for smaller size files. Please resort to other methods such as cloud storage or scp to download larger files.

If results.csv is large, consider writing it to cloud storage from within the container instead, or using scp. model.pt files can also be large on the upload side — there's no explicit size warning for upload() in the artifact, but the same practical limits apply. |  | 2 | Correct + flags the artifact's file-size warning. |
| P10 | Container | S1 · Chatbot (blind) | To tear everything down, specifically removing the CHI@Edge container and freeing the device, the primary documentation provided does not offer direct instructions on how to accomplish this task through the Graphical User Interface (GUI) or any other method. The documentation focuses on the overview of the GUI interface, navigation, and basic functionality, along with references to more detailed sections on specific features like bare metal instances, networking, and reservations. However, it does not explicitly cover the process of tearing down resources like the CHI@Edge container.

Given the information available, it seems that detailed instructions for removing specific resources or containers, such as CHI@Edge, are not provided in the primary documentation passage. For accurate and detailed steps on how to remove the CHI@Edge container and free the device, it would be necessary to consult more specific documentation sections or resources that are not included in the provided primary documentation.

Therefore, based on the information given, I don't know the exact steps to tear everything down as requested.

Further Reading
DocsGui |  | 0 | Admits no knowledge; references docs only. |
| P10 | Container | S1 · Chatbot (artifact) | To tear everything down, you need to remove the CHI@Edge container and free the device.

Here are the steps to follow:

Delete the container: my_container.delete()
Delete the lease: my_lease.delete()
These steps will ensure that the container is removed and the device is freed, making it available for other users.

Here is the code:

my_container.delete()
my_lease.delete()

Further Reading
DocsGui
BlogChi In A Box Update
BlogCloud Wrangling Chameleons Python Library
BlogExperiment Patterns Making Complex Experiments Easy
BlogConducting Research On The Edge Chiedge
DocsGetting Started

 |  | 2 | Most concise correct answer. |
| P10 | Container | S2 · GPT (blind) | No access to any device, runtime, or container orchestration layer.

If this is about a local setup, the action depends on what “CHI@Edge” is running on:

Docker:
docker ps -a → find container
docker stop <id>
docker rm <id>
Kubernetes:
kubectl get pods -A | grep CHI
kubectl delete pod <name> or deployment
System service (Linux):
systemctl stop chi-edge
systemctl disable chi-edge
rm -rf /opt/chi-edge (only if you really intend full removal)

If you share the environment (Docker, k8s, bare metal, cloud vendor), I can give the exact teardown sequence without guesswork. |  | 0 | Generic Docker/K8s/systemctl; wrong tool entirely. |
| P10 | Container | S2 · GPT (artifact) | Tear down sequence (CHI@Edge / python-chi)

To fully release resources, you remove the container first, then delete the lease.

# remove container (stops workload + detaches from reservation)
my_container.delete()

# free the reserved Pi + camera device
my_lease.delete()
What this does
my_container.delete()
Stops and removes the running container bound to the pi_libcamera device profile.
my_lease.delete()
Releases the iot-rpi4-picam* Raspberry Pi 4 back into the pool, freeing the camera-equipped node.

That completes cleanup and returns the edge device to available state. |  | 2 | Correct + clear ordering rationale. |
| P10 | Container | S3 · Claude (blind) | I don't have a connection to CHI@Edge or the Chameleon Cloud API, so I can't directly tear down your container or release the device. Here's how to do it yourself:
Via the CLI (recommended)
If you're using the chi CLI or OpenStack client:
bash# List your containers to confirm the name/ID
openstack --os-cloud chi@edge container list

# Delete the container
openstack --os-cloud chi@edge container delete <container-name-or-id>

# Release the lease (frees the device)
openstack --os-cloud chi@edge reservation lease delete <lease-name-or-id>
Or with the Zun client directly:
bashopenstack --os-cloud chi@edge appcontainer delete --force <container-name-or-id>
Via the Chameleon Portal

Go to chi.edge.chameleoncloud.org
Containers → Containers → find your container → Delete
Reservations → Leases → find your lease → Delete Lease

Deleting the lease is the key step to actually free the physical device — just stopping or deleting the container alone won't release it back to the pool.
Double-check before deleting
bash# Confirm no important data/logs you need
openstack --os-cloud chi@edge appcontainer logs <container-name>
Want help with anything else, like setting up a new lease or writing a teardown script you can reuse? |  | 0 | OpenStack CLI; wrong API though right concept (container then lease). |
| P10 | Container | S3 · Claude (artifact) | 
python
my_container.delete()
my_lease.delete()
That's the full cleanup. my_container.delete() stops and removes the running container from CHI@Edge, and my_lease.delete() releases the device reservation, freeing the iot-rpi4-picam* Raspberry Pi 4 back to the pool. |  | 2 | Cleanest — just the two correct calls. |
| P11 | SSH / Dev | S1 · Chatbot (blind) | To launch an SSH-enabled container on a reserved Pi and connect to it, follow these steps:

Reserve a node: Reserve a Raspberry Pi node on Chameleon Cloud.
Launch an instance: Launch an instance on the reserved node. Ensure that the instance is configured to allow SSH connections.
Associate a floating IP: Associate a floating IP with the instance.
Connect via SSH: Open a terminal and connect to the instance using the private key you added during the launch step. The default login username is cc. Use the following command:
ssh -i /path/to/your/private/key cc@<your-floating-ip>

Replace /path/to/your/private/key with the path to your private key file and <your-floating-ip> with the floating IP you associated in the previous step.
Note: The provided primary documentation does not specifically mention launching a container on a reserved Pi. However, it does provide general guidance on launching an instance and connecting via SSH. For more specific information on launching containers, you may need to refer to additional documentation or resources.

Further Reading
DocsGetting Started

 |  | 0 | Generic SSH/key-pair advice; doesn't know edge_ssh_image; no python-chi code. |
| P11 | SSH / Dev | S1 · Chatbot (artifact) | To launch an SSH-enabled container on a reserved Pi and connect to it, follow these steps:

Select the Chameleon site: Use chi.use_site("CHI@Edge") to select the CHI@Edge site.
Set the project name: Use chi.set("project_name", "Chameleon") to set the project name.
Create a 1-day lease: Use lease.lease_duration(days=1) to create a 1-day lease for a Raspberry Pi 4 device. Then, use lease.add_device_reservation and lease.create_lease to create the lease.
Wait for the lease to become active: Use lease.wait_for_active(lease_id) to wait for the lease to become active.
Create a container: Use container.create_container to create a container with the image ghcr.io/chameleoncloud/edge_ssh_image:latest, exposed port 22, and other required arguments.
Upload your public key: Use chi.container.upload to upload your public key to the container.
Set permissions and append the key to authorized_keys: Use chi.container.execute to set permissions and append the key to authorized_keys.
Associate a floating IP: Use chi.container.associate_floating_ip to associate a floating IP with the container.
Connect to the container: Use the command ssh root@<ip> to connect to the container, where <ip> is the floating IP associated with the container.
Note: Replace <ip> with the actual IP address associated with the container. The IP address can be obtained using chi.container.associate_floating_ip(my_container.uuid).

Further Reading
DocsGui
BlogChi In A Box Update
DocsFederation
DocsGetting Started
BlogSeamless Ssh Container Access With Chiedge
BlogBack To School With Chameleon

 |  | 1 | Right components listed in prose; no actual code block — not directive enough. |
| P11 | SSH / Dev | S2 · GPT (blind) | You don’t “enable SSH in a container” by default—you build or run a container that already runs an SSH daemon and expose its port from the Pi.

Here are two clean ways.

Option 1: Fastest (prebuilt SSH container)

On the Raspberry Pi:

docker run -d \
  --name ssh-pi \
  -p 2222:22 \
  rastasheep/ubuntu-sshd:18.04

This image already runs sshd.

Set a password (inside container)
docker exec -it ssh-pi bash
passwd
Option 2: Proper setup (recommended, key-based)
1. Dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y openssh-server \
    && mkdir /var/run/sshd

RUN useradd -m -s /bin/bash dev && echo "dev:dev" | chpasswd

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D"]
2. Build + run on Pi
docker build -t pi-ssh .
docker run -d \
  --name pi-ssh \
  -p 2222:22 \
  pi-ssh
Connect to it

First, find the Pi’s IP:

hostname -I

Then from your machine:

Password login
ssh dev@<PI_IP> -p 2222

Password: dev

Better: SSH key login (recommended)

On your laptop:

ssh-keygen
ssh-copy-id -p 2222 dev@<PI_IP>

Then connect:

ssh dev@<PI_IP> -p 2222
Common failure points
Port 2222 not open → firewall or router blocking it
Container not running → docker ps

SSH service not started → check logs:

docker logs ssh-pi

If you meant a managed “reserved Pi” environment (cloud-hosted or orchestrated), the exact launch method changes (often it’s Kubernetes or a vendor API rather than raw Docker). |  | 0 | Generic rastasheep docker image; port 2222; misses edge_ssh_image. |
| P11 | SSH / Dev | S2 · GPT (artifact) | Below is the exact CHI@Edge flow from the artifact, rewritten as a single runnable sequence plus the final SSH command.

1. Select site and project
import chi
from chi import lease, container

chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")
2. Create a 1-day Pi lease
machine_name = "raspberrypi4-64"

start, end = lease.lease_duration(days=1)

lease_name = f"ssh-{machine_name}-{start}"

reservations = []
lease.add_device_reservation(reservations, count=2, machine_name=machine_name)

container_lease = lease.create_lease(lease_name, reservations)
lease_id = container_lease["id"]

lease.wait_for_active(lease_id)
3. Start SSH-enabled container on the reserved Pi
container_name = f"edge-{machine_name}-ssh".replace("_", "-")

my_container = container.create_container(
    container_name,
    image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
    workdir="/home",
    exposed_ports=[22],
    reservation_id=lease.get_device_reservation(lease_id),
    platform_version=2,
)
4. Inject your SSH public key

Prepare a local file:

edge_user_public_key

It must contain a single RSA public key line like:

ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC...

Then upload + install it:

chi.container.upload(my_container.uuid, "./edge_user_public_key", "/root/.ssh/")

chi.container.execute(
    my_container.uuid,
    '/bin/bash -c "chmod 600 /root/.ssh/authorized_keys"'
)

chi.container.execute(
    my_container.uuid,
    '/bin/bash -c "cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys"'
)
5. Attach floating IP and get SSH endpoint
ip_address = chi.container.associate_floating_ip(my_container.uuid)

print("SSH command:")
print(f"ssh root@{ip_address}")
6. Connect

From your terminal:

ssh root@<printed-ip>
Optional cleanup
chi.container.destroy_container(my_container.uuid)
What this gives you
A reserved Raspberry Pi 4 on CHI@Edge
An Ubuntu-based container with sshd running on port 22
Root SSH access via your injected RSA key
A floating IP for direct external connection |  | 2 | Correct full workflow with edge_ssh_image + ssh root@<ip>. |
| P11 | SSH / Dev | S3 · Claude (blind) | I don't have access to your Raspberry Pi infrastructure, so I can't directly launch containers or connect to reserved Pi devices. This would require tools or credentials specific to your setup.
That said, here's how you can do it yourself depending on your stack:
If you're using Docker on the Pi:
bashdocker run -d \
  --name my-ssh-container \
  -p 2222:22 \
  linuxserver/openssh-server
Then connect with: ssh user@<pi-ip> -p 2222
If you're using a Pi provisioning tool (like Balena, Raspberry Pi Imager, or a custom fleet manager), the steps vary — let me know which one and I can give exact instructions.
To find your Pi's IP:
bash# On your local network
ping raspberrypi.local
# or check your router's DHCP table
What would help me assist you better:

What container runtime are you using? (Docker, Podman, containerd, Balena)
Is the Pi already running and accessible, or does it need to be provisioned?
Do you have a specific base image in mind for the SSH container?

Give me those details and I can write the exact commands for your setup. |  | 0 | Generic linuxserver/openssh image; misses CHI@Edge specifics. |
| P11 | SSH / Dev | S3 · Claude (artifact) | Launching an SSH-enabled container on CHI@Edge
Here's the complete workflow, based on the edge_ssh_image artifact.

1. Setup
pythonimport chi
from chi import container, lease

chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")

2. Create a 1-day device lease
This reserves two raspberrypi4-64 devices (only one will be used for the container):
pythonmachine_name = "raspberrypi4-64"

start, end = lease.lease_duration(days=1)
lease_name = f"ssh-{machine_name}-{start}"

reservations = []
lease.add_device_reservation(reservations, count=2, machine_name=machine_name)

container_lease = lease.create_lease(lease_name, reservations)
lease_id = container_lease["id"]

print(f"Created lease {lease_name} ({lease_id}), waiting for it to become active…")
lease.wait_for_active(lease_id)
print("Lease is active!")

3. Launch the SSH container
The image is a pre-built Ubuntu 22.04 with sshd configured for root login:
pythoncontainer_name = f"tutorial-{machine_name}-ssh".replace("_", "-")

try:
    my_container = container.create_container(
        container_name,
        image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
        workdir="/home",
        exposed_ports=[22],
        reservation_id=lease.get_device_reservation(lease_id),
        platform_version=2,
    )
except RuntimeError as ex:
    print(ex)
    print(f"Stop/delete '{container_name}' and retry.")
else:
    print(f"Container '{container_name}' created!")

Image download can take several minutes the first time.


4. Inject your public key
Before running this step, edit the file ./edge_user_public_key and replace its placeholder content with your actual one-line RSA public key (e.g. ssh-rsa AAAA…).
python# Upload the key file into the container
chi.container.upload(my_container.uuid, "./edge_user_public_key", "/root/.ssh/")

# Set correct permissions on authorized_keys
chi.container.execute(my_container.uuid,
    '/bin/bash -c "chmod 600 /root/.ssh/authorized_keys"')

# Append your key to authorized_keys
chi.container.execute(my_container.uuid,
    '/bin/bash -c "cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys"')

5. Attach a floating IP and connect
pythonip_address = chi.container.associate_floating_ip(my_container.uuid)
print(f"ssh root@{ip_address}")
Then on your local machine:
bashssh root@<ip_address>

If the connection hangs indefinitely, release the floating IP via the CHI@Edge OpenStack dashboard and re-run associate_floating_ip.


6. Cleanup when done
pythonchi.container.destroy_container(my_container.uuid)

How it all fits together
WhatValueSiteCHI@EdgeDevice typeraspberrypi4-64 (×2 reserved, ×1 used)Container imageghcr.io/chameleoncloud/edge_ssh_image:latestExposed port22 (SSH)Loginroot + your RSA keyLease duration1 day
The container image is Ubuntu 22.04 with PermitRootLogin yes and sshd -D as its entrypoint — no password needed, just your key pair. |  | 2 | Comprehensive correct workflow + summary table. |
| P12 | SSH / Dev | S1 · Chatbot (blind) |  |  |  |  |
| P12 | SSH / Dev | S1 · Chatbot (artifact) |  |  |  |  |
| P12 | SSH / Dev | S2 · GPT (blind) |  |  |  |  |
| P12 | SSH / Dev | S2 · GPT (artifact) |  |  |  |  |
| P12 | SSH / Dev | S3 · Claude (blind) |  |  |  |  |
| P12 | SSH / Dev | S3 · Claude (artifact) |  |  |  |  |
| P13 | SSH / Dev | S1 · Chatbot (blind) |  |  |  |  |
| P13 | SSH / Dev | S1 · Chatbot (artifact) |  |  |  |  |
| P13 | SSH / Dev | S2 · GPT (blind) |  |  |  |  |
| P13 | SSH / Dev | S2 · GPT (artifact) |  |  |  |  |
| P13 | SSH / Dev | S3 · Claude (blind) |  |  |  |  |
| P13 | SSH / Dev | S3 · Claude (artifact) |  |  |  |  |
| P14 | SSH / Dev | S1 · Chatbot (blind) | To get a Raspberry Pi on CHI@Edge that you can access with VS Code Remote-SSH, follow these steps:

Create a CHI@Edge Site: First, ensure you have a CHI@Edge site set up. This involves registering your edge site and configuring it according to the CHI@Edge documentation.

Provision a Raspberry Pi: Provision a Raspberry Pi at your edge site. This typically involves flashing the Pi with an appropriate operating system (like Raspberry Pi OS) and ensuring it has network connectivity.

Install CHI@Edge Agent: Install the CHI@Edge agent on your Raspberry Pi. The agent allows your Pi to communicate with the CHI@Edge control plane, enabling you to manage it remotely.

Configure SSH on the Raspberry Pi: Ensure SSH is enabled on your Raspberry Pi. This is usually enabled by default, but you may need to configure it to allow passwordless SSH login using keys.

Generate SSH Keys: Generate a pair of SSH keys on your local machine if you haven't already. You'll need the public key to configure passwordless SSH login on your Raspberry Pi.

Add SSH Key to Raspberry Pi: Copy the public SSH key to your Raspberry Pi (typically to the .ssh/authorized_keys file of the user you intend to log in as) to enable passwordless SSH login.

Install VS Code and Remote-SSH Extension: On your local machine, install Visual Studio Code (VS Code) and the Remote-SSH extension. This extension allows you to connect to your Raspberry Pi remotely.

Configure VS Code Remote-SSH: Configure the Remote-SSH extension in VS Code by adding a new SSH host that points to your Raspberry Pi's IP address or hostname. You'll need to specify the username you'll use to log in and the path to your private SSH key.

Connect to Raspberry Pi with VS Code: Open VS Code, and using the Command Palette or the Remote Explorer, connect to your Raspberry Pi. Once connected, you can open folders, edit files, and use the terminal directly on your Raspberry Pi as if you were sitting in front of it.

By following these steps, you should be able to set up a Raspberry Pi on CHI@Edge and access it using VS Code Remote-SSH for development and management purposes. |  | 0 | Treats it as a physical Pi setup (flashing OS); wrong context entirely. |
| P14 | SSH / Dev | S1 · Chatbot (artifact) | To get a Raspberry Pi on CHI@Edge that you can access with VS Code Remote-SSH, follow these steps based on the provided artifact and documentation:

Select the CHI@Edge Site: Use the chi.use_site("CHI@Edge") function to select the CHI@Edge site.

Set the Project Name: Set the project name to "Chameleon" using chi.set("project_name", "Chameleon").

Create a Lease: Create a 1-day lease for a Raspberry Pi 4 device. First, define the machine name as "raspberrypi4-64" and then use lease.lease_duration(days=1) to get the start and end dates for the lease. Create a unique lease name and add a device reservation for the Raspberry Pi 4 with count=2. Then, create the lease using lease.create_lease(lease_name, reservations).

Wait for the Lease to Become Active: Use lease.wait_for_active(lease_id) to wait for the lease to become active.

Create a Container: Create a container using the container.create_container function, specifying the container name, image as "ghcr.io/chameleoncloud/edge_ssh_image:latest", work directory as "/home", exposed ports as [22], and the reservation ID obtained from lease.get_device_reservation(lease_id). Also, specify platform_version=2.

Upload Your Public Key: Upload your RSA public key to the container using chi.container.upload(my_container.uuid, "./edge_user_public_key", "/root/.ssh/").

Set Permissions and Append to Authorized Keys: Execute commands inside the container to set the permissions of the authorized keys file to 600 and append your public key to it using chi.container.execute.

Associate a Floating IP: Associate a floating IP with the container using chi.container.associate_floating_ip(my_container.uuid) to get an IP address you can use to SSH into the container.

SSH into the Container: Use the IP address obtained and the command ssh root@<ip_address> to connect to your Raspberry Pi on CHI@Edge.

Destroy the Container: When you're done, destroy the container using chi.container.destroy_container(my_container.uuid) to free up resources.

This process should give you a Raspberry Pi on CHI@Edge that you can access with VS Code Remote-SSH. Remember to replace the placeholder in the edge_user_public_key file with your actual RSA public key before uploading it.

Further Reading
DocsGui
BlogChi In A Box Update
DocsFederation
DocsGetting Started
BlogSeamless Ssh Container Access With Chiedge
BlogBack To School With Chameleon

 |  | 1 | Right workflow in prose; misses VS Code config step; no code block. |
| P14 | SSH / Dev | S2 · GPT (blind) | Here’s the clean end-to-end path to get a Raspberry Pi running on CHI@Edge and accessible via VS Code Remote-SSH.

1. What you’re actually building

You need 3 pieces:

A Raspberry Pi (Edge node)
CHI@Edge allocation (Kubernetes-backed edge slice)
SSH entry path from your laptop → CHI gateway → Pi

What this really means: your Pi must be reachable via a routable IP inside CHI@Edge or via a forwarded SSH service.

2. Prereqs (don’t skip this)
Hardware
Raspberry Pi 4/5 recommended
Ethernet preferred (WiFi works but adds friction)
Software on Pi

Flash Raspberry Pi OS Lite (64-bit).

During imaging:

Enable SSH
Set username/password or inject SSH key

After boot:

sudo apt update
sudo apt install -y openssh-server

Confirm:

systemctl status ssh
3. Get access to CHI@Edge

You need:

CHI account (CHameleon cloud)
Project allocation with CHI@Edge enabled

Inside CHI dashboard:

Go to CHI@Edge → Devices / Sites
Reserve or register a node (your Pi or a gateway node depending on setup)

Two common models:

A. Direct Pi in edge network (best case)
Pi is registered as an edge device
Gets CHI-assigned IP or DHCP lease in edge subnet
B. Pi behind a CHI gateway node (more common)
You SSH into a CHI VM/gateway first
Then hop to Pi over private edge network
4. Put Pi on CHI@Edge network
Option A: DHCP (simplest)

Plug Pi into CHI edge LAN.

On Pi:

ip a

Look for assigned IP like:

10.x.x.x / 192.168.x.x (CHI internal range)

Test gateway reachability:

ping <chi-gateway-ip>
Option B: Static IP (if required by CHI setup)

Edit:

sudo nano /etc/dhcpcd.conf

Example:

interface eth0
static ip_address=10.20.0.50/24
static routers=10.20.0.1
static domain_name_servers=8.8.8.8

Restart:

sudo reboot
5. SSH access setup
On Pi

Make sure your key is installed:

mkdir -p ~/.ssh
nano ~/.ssh/authorized_keys

Paste your laptop public key.

Fix permissions:

chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
From laptop test
ssh pi@<pi-ip>

If CHI requires jump host:

ssh -J user@chi-gateway user@10.x.x.x
6. Make VS Code Remote-SSH work

Install extension:

Remote - SSH (Microsoft)

Then configure:

code ~/.ssh/config

Add:

Direct Pi
Host chi-pi
  HostName 10.x.x.x
  User pi
  IdentityFile ~/.ssh/id_rsa
Via CHI gateway
Host chi-gateway
  HostName <gateway-public-ip>
  User <your-user>

Host chi-pi
  HostName 10.x.x.x
  User pi
  ProxyJump chi-gateway

Then connect:

Ctrl+Shift+P
Remote-SSH: Connect to Host
Select chi-pi

VS Code will install server-side components automatically.

7. Common CHI@Edge pitfalls
No IP assigned
Pi not on correct VLAN / port
Edge switch port not activated in CHI portal
SSH timeout
Firewall blocking port 22 inside edge network
Missing ProxyJump through CHI gateway
VS Code fails but SSH works
Usually shell startup issues
Fix:
echo 'exec bash' >> ~/.bashrc
8. Minimal sanity checklist
 Pi reachable via ping
 ssh pi@ip works locally
 CHI gateway reachable (if used)
 SSH key auth works (no password prompts)
 VS Code config uses correct HostName or ProxyJump

If you want, next step is tighter automation:

Terraform CHI@Edge + Pi provisioning pattern
or k3s cluster with Pi as edge worker node
or zero-trust SSH (tailscale/nebula overlay instead of CHI routing)

Just say which direction. |  | 0 | Treats Pi as a LAN device; talks about DHCP and routers; wrong context. |
| P14 | SSH / Dev | S2 · GPT (artifact) | Goal: provision a CHI@Edge Raspberry Pi container and make it reachable via SSH in a way that VS Code Remote-SSH can use.

What follows is the end-to-end sequence, aligned exactly with the CHI@Edge functional python-chi workflow from your artifact, with only the additions needed for VS Code compatibility (SSH key + stable IP + SSH config behavior).

1. Set site and project
import chi
from chi import lease, container

chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")
2. Create a 1-day Raspberry Pi lease

Key constraint from the artifact: raspberrypi4-64, count=2, no device profiles.

machine_name = "raspberrypi4-64"
start, end = lease.lease_duration(days=1)

lease_name = f"vscode-ssh-{machine_name}-{start}"

reservations = []
lease.add_device_reservation(reservations, count=2, machine_name=machine_name)

container_lease = lease.create_lease(lease_name, reservations)
lease_id = container_lease["id"]

lease.wait_for_active(lease_id)

At this point you have two reserved Pi devices. One will be bound to the container.

3. Start SSH-enabled container on the reserved Pi

Important fields (from artifact):

image: ghcr.io/chameleoncloud/edge_ssh_image:latest
exposed_ports: [22]
platform_version: 2
reservation_id from lease
container_name = f"vscode-{machine_name}-ssh".replace("_", "-")

my_container = container.create_container(
    container_name,
    image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
    workdir="/home",
    exposed_ports=[22],
    reservation_id=lease.get_device_reservation(lease_id),
    platform_version=2,
)
4. Inject your SSH key (VS Code requirement)

VS Code Remote-SSH requires a normal OpenSSH keypair.

Create or reuse:

ssh-keygen -t rsa -b 4096 -f ~/.ssh/chi_edge

Then write the public key into:

edge_user_public_key

(one line, no newline breaks)

Upload + install it:

chi.container.upload(my_container.uuid, "./edge_user_public_key", "/root/.ssh/")

chi.container.execute(
    my_container.uuid,
    '/bin/bash -c "chmod 600 /root/.ssh/authorized_keys"'
)

chi.container.execute(
    my_container.uuid,
    '/bin/bash -c "cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys"'
)
5. Attach floating IP (this is your VS Code target host)
ip_address = chi.container.associate_floating_ip(my_container.uuid)
print(ip_address)

This IP is the only thing VS Code needs.

6. Test raw SSH first (mandatory sanity check)
ssh -i ~/.ssh/chi_edge root@<IP>

If this fails, VS Code will fail too.

7. VS Code Remote-SSH config

Edit:

~/.ssh/config

Add:

Host chi-edge-pi
    HostName <IP>
    User root
    IdentityFile ~/.ssh/chi_edge
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null

Then in VS Code:

Command Palette → Remote-SSH: Connect to Host
Select chi-edge-pi
8. Clean teardown (important on CHI@Edge)
chi.container.destroy_container(my_container.uuid)

Also release lease if your workflow requires explicit cleanup in your environment.

What actually matters for VS Code success

Only three things are critical:

Container must expose port 22 (edge_ssh_image already does this)
Public key must be correctly appended to /root/.ssh/authorized_keys
Floating IP must be reachable from your local machine

Everything else is orchestration.

If you want, I can modify this into a single reusable function like provision_chi_edge_pi_for_vscode() that returns a ready SSH config block automatically. |  | 2 | Complete + adds VS Code ~/.ssh/config block. |
| P14 | SSH / Dev | S3 · Claude (blind) | Here's the full end-to-end walkthrough — from zero to VS Code connected to a Pi on CHI@Edge.

Prerequisites

Chameleon Cloud account at chameleoncloud.org with a project that has a CHI@Edge allocation
python-chi and OpenStack CLI tools (or just the web GUI — covered below)
Your SSH public key uploaded to the portal


Step 1 — Upload your SSH key

Go to chi.edge.chameleoncloud.org
Project → Compute → Key Pairs → Import Public Key
Paste your ~/.ssh/id_ed25519.pub (or RSA). Note the key name — you'll use it below.


Step 2 — Reserve a Raspberry Pi node
CHI@Edge uses Blazar for advance reservations. You must hold a lease before you can launch anything.
Via the GUI (Experiment → Reservations → Leases → Create Lease):
FieldValueLease namemy-pi-leaseStartnow (or scheduled)End+1 day (max varies by allocation)Resource typedeviceMachine name / filterraspberrypi4-64 (or leave blank to get any Pi)Min/Max count1
Hit Create and wait for status → ACTIVE (usually < 2 min).
Via CLI (python-chi):
pythonimport chi
from chi import lease

chi.use_site("CHI@Edge")
chi.set("project_name", "YOUR_PROJECT")

my_lease = lease.create_lease("my-pi-lease", reservations=[
    lease.device_reservation(min=1, max=1, machine_name="raspberrypi4-64")
])
lease.wait_for_active(my_lease["id"])
print("Reservation ID:", lease.get_device_reservation(my_lease["id"]))

Step 3 — Launch a container on the Pi
CHI@Edge runs containers (Zun), not VMs. Pick an arm64 image with an SSH daemon.
Via GUI (Experiment → Container → Containers → Create Container):
FieldValueNamemy-piImageubuntu:22.04 (arm64 — Chameleon pulls the right arch)Reservationselect the lease you just createdExposed ports22Command(leave blank — we'll install sshd below)
→ After creation, open a Console session and run:
bashapt-get update && apt-get install -y openssh-server
mkdir -p /root/.ssh
echo "YOUR_PUBLIC_KEY_HERE" >> /root/.ssh/authorized_keys
chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys
service ssh start
Via CLI:
pythonfrom chi import container

c = container.create_container(
    name="my-pi",
    image="ubuntu:22.04",
    exposed_ports=[22],
    reservation_id=RESERVATION_ID,   # from step 2
    platform_version=2,
)
container.wait_for_active(c["uuid"])
Then exec into it to set up sshd as above.

Step 4 — Attach a floating IP
bash# Get the container's network port
openstack port list --device-id <container-uuid>

# Allocate a floating IP from the public pool
openstack floating ip create public

# Associate it
openstack floating ip set --port <port-id> <floating-ip>
Via GUI: Container detail page → Associate Floating IP → allocate from public pool.
Note the floating IP — e.g. 192.5.87.42.

Step 5 — Verify SSH access
bashssh -i ~/.ssh/id_ed25519 root@192.5.87.42
If the firewall blocks you, add a security group rule:
bashopenstack security group rule create default \
  --protocol tcp --dst-port 22 --remote-ip 0.0.0.0/0
openstack server add security group <container-uuid> default

Step 6 — Configure VS Code Remote-SSH
Add this to your ~/.ssh/config:
sshHost chameleon-pi
    HostName 192.5.87.42        # your floating IP
    User root
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 3
Then in VS Code:

Install the Remote - SSH extension (ms-vscode-remote.remote-ssh)
Ctrl/Cmd + Shift + P → Remote-SSH: Connect to Host…
Select chameleon-pi
VS Code will install the Remote-SSH server on the Pi automatically — takes ~1 min on first connect

You'll land in a full VS Code session running natively on the Pi's arm64 hardware.

Tips & Gotchas
IssueFixLease won't activateCheck your project's CHI@Edge allocation balance at the portalarm64 image failsSpecify arm64v8/ubuntu:22.04 explicitly if auto-detect failsVS Code server install failsThe Pi needs outbound internet; verify with curl https://update.code.visualstudio.com from the containerFloating IP quotaEach project gets a small quota; release unused IPs with openstack floating ip deleteLease expires mid-workRenew via Leases → Update Lease → extend end time before it expires — the container survives lease renewal

Once you're connected, VS Code Remote-SSH gives you full IntelliSense, the integrated terminal, port forwarding, and extension support running directly on the Pi hardware. Let me know if you hit a snag at any step. |  | 1 | Surprisingly close — knows Blazar/Zun exist; some invented params. |
| P14 | SSH / Dev | S3 · Claude (artifact) | Here's the complete end-to-end setup, built directly from the artifact's API calls.

1. Prerequisites
Local machine:

Python env with python-chi installed (pip install python-chi)
VS Code with the Remote - SSH extension
An RSA key pair — if you don't have one: ssh-keygen -t rsa -b 4096 -f ~/.ssh/chi_edge


2. Prepare your public key file
The artifact uploads a file called edge_user_public_key. Create it now:
bashcp ~/.ssh/chi_edge.pub ./edge_user_public_key

The placeholder in the artifact says replace this line with your RSA public key — this step is what replaces it.


3. Run the notebook / script
pythonimport chi
from chi import container, lease

# ── Site & project ──────────────────────────────────────────────────────────
chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")   # change if your project name differs

# ── Lease (1 day, 2× raspberrypi4-64) ───────────────────────────────────────
machine_name = "raspberrypi4-64"
start, end   = lease.lease_duration(days=1)
lease_name   = f"ssh-{machine_name}-{start}"

reservations = []
lease.add_device_reservation(reservations, count=2, machine_name=machine_name)
container_lease = lease.create_lease(lease_name, reservations)
lease_id = container_lease["id"]

print(f"Lease {lease_name} ({lease_id}) created — waiting for ACTIVE (up to 60 s)…")
lease.wait_for_active(lease_id)
print("Lease is active.")

# ── Container ────────────────────────────────────────────────────────────────
container_name = f"tutorial-{machine_name}-ssh".replace("_", "-")

try:
    my_container = container.create_container(
        container_name,
        image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
        workdir="/home",
        exposed_ports=[22],
        reservation_id=lease.get_device_reservation(lease_id),
        platform_version=2,
    )
except RuntimeError as ex:
    print(ex)
    raise SystemExit(f"Stop/delete {container_name} then retry.")

print(f"Container ready: {my_container.uuid}")

# ── Inject your public key ───────────────────────────────────────────────────
chi.container.upload(my_container.uuid, "./edge_user_public_key", "/root/.ssh/")
chi.container.execute(my_container.uuid,
    '/bin/bash -c "chmod 600 /root/.ssh/authorized_keys"')
chi.container.execute(my_container.uuid,
    '/bin/bash -c "cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys"')

# ── Floating IP ──────────────────────────────────────────────────────────────
ip = chi.container.associate_floating_ip(my_container.uuid)
print(f"\n✅  ssh root@{ip}")
print(f"    (private key: ~/.ssh/chi_edge)")

4. Verify SSH works first
bashssh -i ~/.ssh/chi_edge -o StrictHostKeyChecking=no root@<IP>
If it hangs at "connecting to device", go to the CHI@Edge OpenStack dashboard, release the floating IP, and re-run only the associate_floating_ip cell.

5. Configure VS Code Remote-SSH
Add this block to your ~/.ssh/config:
Host chi-edge-pi
    HostName <IP from step 4>
    User root
    IdentityFile ~/.ssh/chi_edge
    ServerAliveInterval 60
    ServerAliveCountMax 5
Then in VS Code:

Ctrl/Cmd+Shift+P → Remote-SSH: Connect to Host…
Pick chi-edge-pi
VS Code will install its server-side agent on the Pi container and open a remote window — you can now open folders, use the terminal, run extensions, etc.


6. Cleanup (when done)
pythonchi.container.destroy_container(my_container.uuid)
Also let the lease expire or delete it via the dashboard to free the devices for others.

Key facts from the artifact
ThingValueDevice typeraspberrypi4-64 (reserved by machine_name, count=2)Device profilesnoneContainer imageghcr.io/chameleoncloud/edge_ssh_image:latestBase OSUbuntu 22.04 + openssh-server (sshd -D)Loginroot (PermitRootLogin enabled in image)Port22 |  | 2 | Complete end-to-end with VS Code config; cleanest of the three. |
| P15 | Peripherals · Camera | S1 · Chatbot (blind) |  |  |  |  |
| P15 | Peripherals · Camera | S1 · Chatbot (artifact) |  |  |  |  |
| P15 | Peripherals · Camera | S2 · GPT (blind) |  |  |  |  |
| P15 | Peripherals · Camera | S2 · GPT (artifact) |  |  |  |  |
| P15 | Peripherals · Camera | S3 · Claude (blind) |  |  |  |  |
| P15 | Peripherals · Camera | S3 · Claude (artifact) |  |  |  |  |
| P16 | Peripherals · Camera | S1 · Chatbot (blind) |  |  |  |  |
| P16 | Peripherals · Camera | S1 · Chatbot (artifact) |  |  |  |  |
| P16 | Peripherals · Camera | S2 · GPT (blind) |  |  |  |  |
| P16 | Peripherals · Camera | S2 · GPT (artifact) |  |  |  |  |
| P16 | Peripherals · Camera | S3 · Claude (blind) |  |  |  |  |
| P16 | Peripherals · Camera | S3 · Claude (artifact) |  |  |  |  |
| P17 | Peripherals · Camera | S1 · Chatbot (blind) |  |  |  |  |
| P17 | Peripherals · Camera | S1 · Chatbot (artifact) |  |  |  |  |
| P17 | Peripherals · Camera | S2 · GPT (blind) |  |  |  |  |
| P17 | Peripherals · Camera | S2 · GPT (artifact) |  |  |  |  |
| P17 | Peripherals · Camera | S3 · Claude (blind) |  |  |  |  |
| P17 | Peripherals · Camera | S3 · Claude (artifact) |  |  |  |  |
| P18 | Peripherals · Camera | S1 · Chatbot (blind) |  |  |  |  |
| P18 | Peripherals · Camera | S1 · Chatbot (artifact) |  |  |  |  |
| P18 | Peripherals · Camera | S2 · GPT (blind) |  |  |  |  |
| P18 | Peripherals · Camera | S2 · GPT (artifact) |  |  |  |  |
| P18 | Peripherals · Camera | S3 · Claude (blind) |  |  |  |  |
| P18 | Peripherals · Camera | S3 · Claude (artifact) |  |  |  |  |
| P19 | Peripherals · Camera | S1 · Chatbot (blind) |  |  |  |  |
| P19 | Peripherals · Camera | S1 · Chatbot (artifact) |  |  |  |  |
| P19 | Peripherals · Camera | S2 · GPT (blind) |  |  |  |  |
| P19 | Peripherals · Camera | S2 · GPT (artifact) |  |  |  |  |
| P19 | Peripherals · Camera | S3 · Claude (blind) |  |  |  |  |
| P19 | Peripherals · Camera | S3 · Claude (artifact) |  |  |  |  |
| P20 | Peripherals · Sense HAT | S1 · Chatbot (blind) |  |  |  |  |
| P20 | Peripherals · Sense HAT | S1 · Chatbot (artifact) |  |  |  |  |
| P20 | Peripherals · Sense HAT | S2 · GPT (blind) |  |  |  |  |
| P20 | Peripherals · Sense HAT | S2 · GPT (artifact) |  |  |  |  |
| P20 | Peripherals · Sense HAT | S3 · Claude (blind) |  |  |  |  |
| P20 | Peripherals · Sense HAT | S3 · Claude (artifact) |  |  |  |  |
| P21 | Peripherals · Sense HAT | S1 · Chatbot (blind) |  |  |  |  |
| P21 | Peripherals · Sense HAT | S1 · Chatbot (artifact) |  |  |  |  |
| P21 | Peripherals · Sense HAT | S2 · GPT (blind) |  |  |  |  |
| P21 | Peripherals · Sense HAT | S2 · GPT (artifact) |  |  |  |  |
| P21 | Peripherals · Sense HAT | S3 · Claude (blind) |  |  |  |  |
| P21 | Peripherals · Sense HAT | S3 · Claude (artifact) |  |  |  |  |
| P22 | Peripherals · Sense HAT | S1 · Chatbot (blind) |  |  |  |  |
| P22 | Peripherals · Sense HAT | S1 · Chatbot (artifact) |  |  |  |  |
| P22 | Peripherals · Sense HAT | S2 · GPT (blind) |  |  |  |  |
| P22 | Peripherals · Sense HAT | S2 · GPT (artifact) |  |  |  |  |
| P22 | Peripherals · Sense HAT | S3 · Claude (blind) |  |  |  |  |
| P22 | Peripherals · Sense HAT | S3 · Claude (artifact) |  |  |  |  |
| P23 | Peripherals · Sense HAT | S1 · Chatbot (blind) |  |  |  |  |
| P23 | Peripherals · Sense HAT | S1 · Chatbot (artifact) |  |  |  |  |
| P23 | Peripherals · Sense HAT | S2 · GPT (blind) |  |  |  |  |
| P23 | Peripherals · Sense HAT | S2 · GPT (artifact) |  |  |  |  |
| P23 | Peripherals · Sense HAT | S3 · Claude (blind) |  |  |  |  |
| P23 | Peripherals · Sense HAT | S3 · Claude (artifact) |  |  |  |  |
| P24 | Peripherals · Sense HAT | S1 · Chatbot (blind) |  |  |  |  |
| P24 | Peripherals · Sense HAT | S1 · Chatbot (artifact) |  |  |  |  |
| P24 | Peripherals · Sense HAT | S2 · GPT (blind) |  |  |  |  |
| P24 | Peripherals · Sense HAT | S2 · GPT (artifact) |  |  |  |  |
| P24 | Peripherals · Sense HAT | S3 · Claude (blind) |  |  |  |  |
| P24 | Peripherals · Sense HAT | S3 · Claude (artifact) |  |  |  |  |
| P25 | Availability | S1 · Chatbot (blind) |  |  |  |  |
| P25 | Availability | S1 · Chatbot (artifact) |  |  |  |  |
| P25 | Availability | S2 · GPT (blind) |  |  |  |  |
| P25 | Availability | S2 · GPT (artifact) |  |  |  |  |
| P25 | Availability | S3 · Claude (blind) |  |  |  |  |
| P25 | Availability | S3 · Claude (artifact) |  |  |  |  |
| P26 | Availability | S1 · Chatbot (blind) | To check whether a given device is free right now on CHI@Edge before reserving, you should refer to the "Reservations" documentation section, as it likely contains detailed instructions on managing and checking the availability of resources, including devices. The primary documentation provided does not specify the exact steps for checking device availability but points towards the dedicated documentation sections for specific features, including reservations. |  | 0 | Refers to docs; doesn't know the API; very short non-answer. |
| P26 | Availability | S1 · Chatbot (artifact) | To check whether a given device is free right now on CHI@Edge before reserving it, you can use the hardware.get_devices() function from the python-chi library. This function allows you to filter devices based on their status, including whether they are currently reserved or available.

Here's a step-by-step approach:

Import necessary modules: Make sure you have imported the necessary modules from the python-chi library, including hardware.

Choose the site: Since you're working with CHI@Edge, you need to choose this site using context.choose_site(default="CHI@Edge").

Select the project: Use context.choose_project() to select the project you're working under.

Filter devices: Use hardware.get_devices() with appropriate filters to find the device you're interested in. For example, if you're looking for a Raspberry Pi 4 with a Pi Camera Module 3 attached, you might filter by device_type="raspberrypi4-64" and then further filter the results to include only devices whose names start with "iot-rpi4-picam".

Check device status: Once you have the list of devices that match your criteria, you can check their status. Devices that are not reserved are considered available.

Here's a simplified example based on the provided context:

from chi import context, hardware

# Choose the site and project
context.choose_site(default="CHI@Edge")
context.choose_project()

# Filter devices
device_type = "raspberrypi4-64"
available_devices = hardware.get_devices(filter_reserved=False, device_type=device_type)

# Further filter to find specific devices
picamera_devs = [d for d in available_devices if d.device_name.startswith("iot-rpi4-picam")]

# Check if there are any available devices
if picamera_devs:
    print("There are available devices.")
else:
    print("No devices are available.")

This example checks for the availability of devices matching the specified criteria on CHI@Edge. Note that the actual implementation might need adjustments based on the exact requirements and the current state of the python-chi library and CHI@Edge testbed.
 |  | 1 | Wrong filter direction (filter_reserved=False instead of True) — logic bug. |
| P26 | Availability | S2 · GPT (blind) | To do that cleanly, you need a real-time availability check against the CHI@Edge device registry before you create any reservation.

Minimal flow
Identify device
Input: device_id (or device name resolved to ID)
Query current state
Call something like:
GET /devices/{device_id}/status
or GET /devices?filter=device_id
Check availability window
Treat device as free right now only if all are true:
status == "available" (or equivalent idle state)
No active reservation overlaps current timestamp
No running job/session attached
Double-check reservation calendar (important)
Query:
GET /reservations?device_id=X&from=now&to=now
Ensure result set is empty
Proceed or block
If free → allow reservation creation
If not free → return next available slot or conflict reason
Pseudocode
def is_device_free(device_id, now):
    status = get_device_status(device_id)
    if status != "available":
        return False

    active_res = get_reservations(device_id, now, now)
    if active_res:
        return False

    return True
Practical note

If CHI@Edge has high concurrency, you should treat this as a race-prone check. The safe pattern is:

Check availability
Attempt reservation
Let backend enforce final lock (atomic reservation creation)

Otherwise two users can pass the check at the same time.

If you want, share the CHI@Edge API shape and I can map this into exact endpoints or a production-safe flow. |  | 0 | All invented APIs (get_device_status, get_reservations); pseudocode. |
| P26 | Availability | S2 · GPT (artifact) | Before reserving a CHI@Edge device, you check availability by querying the hardware inventory with filter_reserved=True and filtering out already-reserved nodes.

Core idea

A device is “free” if:

It appears in hardware.get_devices(...)
It is not currently reserved
It is not already selected by an existing lease
Step-by-step (from the artifact pattern)
from chi import hardware

device_type = "raspberrypi4-64"

# Only devices that are currently not reserved
available_devices = hardware.get_devices(
    filter_reserved=True,
    device_type=device_type
)

At this point:

available_devices contains only devices that are not part of an active reservation
This is your first-level availability filter
Narrow to camera-capable nodes (optional but required for this artifact)
picamera_devs = [
    d for d in available_devices
    if d.device_name.startswith("iot-rpi4-picam")
]

Now:

picamera_devs = devices that are both free and camera-equipped
Final availability check before leasing

You explicitly validate list size:

if len(picamera_devs) == 0:
    raise RuntimeError("No free Pi Camera devices available")
What this means operationally
filter_reserved=True is the primary gate for “is it free”
Device naming (iot-rpi4-picam*) is a hardware-level constraint for camera nodes
CHI does not require a separate “ping availability” step beyond this API call; reservation state is the source of truth
If you want stricter correctness (race-condition safe pattern)

Between checking and leasing, another user may grab the device. The artifact handles this implicitly via:

my_lease.submit(idempotent=True)

That call ensures:

If the device was taken in between, submission fails cleanly or retries safely depending on backend state

If you want, I can show a hardened “check + reserve + retry loop” pattern used in production CHI scripts. |  | 2 | Correct: filter_reserved=True + explains TOCTOU race. |
| P26 | Availability | S3 · Claude (blind) | There's no MCP connector available for CHI@Edge. I can help you check device availability by building a small tool that queries the CHI@Edge API directly.
CHI@Edge (part of the Chameleon testbed) exposes a Blazar (reservation service) and an OpenStack API. Here's a React artifact that lets you check device availability before reserving:
  ::view-transition-group(*),
  ::view-transition-old(*),
  ::view-transition-new(*) {
    animation-duration: 0.25s;
    animation-timing-function: cubic-bezier(0.19, 1, 0.22, 1);
  }
VvisualizeVvisualize show_widgetCHI@Edge device availability checker — check if a device is free before reserving
Authentication
Token
Paste your CHI@Edge OpenStack token (OS_AUTH_TOKEN)
Site

CHI@Edge (chi.edge.chameleoncloud.org)
Get your token: openstack token issue -f value -c id or from the Chameleon dashboard → API Access.

Device filter (optional)
Node name
e.g. jetson-nano-01  (leave blank to list all)
Node type
e.g. container  (leave blank for all types)
Check availability now ↗Here's how it works:
What it checks: It hits two CHI@Edge APIs simultaneously — the Blazar lease service (/v1/leases) to find all active reservations, and the Nova hypervisor list (or Blazar's /v1/hosts as fallback) to enumerate nodes. A node is marked free if no currently-active lease covers it right now.
To use it:

Get your token from the Chameleon dashboard (API Access tab) or run openstack token issue -f value -c id in a shell with your CHI@Edge credentials sourced.
Paste the token, pick your site, and optionally filter by node name or type.
Hit Check availability now.

CORS caveat: Browser-side requests to CHI@Edge APIs may be blocked by CORS headers depending on your browser. If that happens, the same logic works cleanly in a Jupyter notebook on the testbed — just swap the fetch() calls for requests.get() with the same headers (X-Auth-Token). |  | 0 | Builds an elaborate HTML widget for raw Blazar/Nova APIs — wildly overcooked. |
| P26 | Availability | S3 · Claude (artifact) | Checking device availability before reserving on CHI@Edge
The artifact's own pattern gives you everything you need. The key is the filter_reserved=True flag in hardware.get_devices() — it returns only unreserved devices. You then check whether your target device name appears in that list.
pythonfrom chi import context, hardware

context.choose_site(default="CHI@Edge")
context.choose_project()

# Returns only devices NOT currently under a lease
available = hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")

# Pull out the picam-capable ones
picamera_devs = [d for d in available if d.device_name.startswith("iot-rpi4-picam")]

# --- Option A: just see what's free ---
print([d.device_name for d in picamera_devs])

# --- Option B: check a specific device ---
target = "iot-rpi4-picam2"
is_free = any(d.device_name == target for d in picamera_devs)
print(f"{target} is {'free' if is_free else 'reserved or unavailable'}")
What's happening
Call / flagEffecthardware.get_devices(device_type="raspberrypi4-64")Lists all RPi 4 nodes at the sitefilter_reserved=TrueExcludes nodes that are currently under an active lease.startswith("iot-rpi4-picam")Narrows to the camera-equipped subset
If picamera_devs is empty (or doesn't contain your target), the device is reserved and you should wait or pick another. Only proceed to lease.Lease(...) / my_lease.add_device_reservation(devices=[picamera_devs[0]]) once the device shows up in the filtered list.
A word of caution
There's a small TOCTOU window: a device that appears free when you call get_devices could be grabbed by another user before your lease.submit() completes. Using my_lease.submit(idempotent=True) (as the artifact does) lets you safely re-run the cell if that race occurs without creating duplicate leases. |  | 2 | Correct + practical 'check specific device' option. |
| P27 | Availability | S1 · Chatbot (blind) |  |  |  |  |
| P27 | Availability | S1 · Chatbot (artifact) |  |  |  |  |
| P27 | Availability | S2 · GPT (blind) |  |  |  |  |
| P27 | Availability | S2 · GPT (artifact) |  |  |  |  |
| P27 | Availability | S3 · Claude (blind) |  |  |  |  |
| P27 | Availability | S3 · Claude (artifact) |  |  |  |  |
| P28 | Pitfall trap | S1 · Chatbot (blind) | To convert your CHI@UC bare-metal script to run on CHI@Edge, you need to consider the differences between the two environments. CHI@UC is a bare-metal cloud, while CHI@Edge is a container-based edge computing testbed.

Here's a step-by-step guide to help you convert your script:

Understand the node types: CHI@Edge has different node types compared to CHI@UC. You need to identify the equivalent node type on CHI@Edge that matches your requirements. You can use the Hardware Discovery page on the Chameleon Portal to explore the available node types on CHI@Edge.
Update the node type: In your script, update the node_type variable to the equivalent node type on CHI@Edge. For example, if you were using compute_skylake on CHI@UC, you may need to use a different node type on CHI@Edge.
Use the correct image: CHI@Edge uses container-based images, whereas CHI@UC uses bare-metal images. You need to update the image_name variable to a container-based image that is compatible with CHI@Edge.
Modify the reservation: CHI@Edge has different reservation requirements compared to CHI@UC. You may need to update the reservations variable to include additional parameters or modify the existing parameters to match the CHI@Edge requirements.
Update the server creation: When creating the server, you need to use the create_server function with the updated reservation_id, image_name, and other parameters that are compatible with CHI@Edge.
Here's an example of how you can modify your script:

import chi

# Set the site to CHI@Edge
chi.use_site('CHI@Edge')

# Define the node type and count
node_type = 'edge_node_type'  # Update to the equivalent node type on CHI@Edge
node_count = 1

# Define the image name
image_name = 'edge_image_name'  # Update to a container-based image compatible with CHI@Edge

# Create a lease with the updated node type and image
reservations = []
chi.lease.add_node_reservation(reservations, count=node_count, node_type=node_type)
start_date, end_date = chi.lease.lease_duration(hours=1)
lease = chi.lease.create_lease('my_lease', reservations, start_date=start_date, end_date=end_date)

# Wait for the lease to become active
chi.lease.wait_for_active(lease.id)

# Create a server with the updated reservation and image
reservation_id = chi.lease.get_node_reservation(lease.id)
server = chi.server.create_server('my_server', reservation_id=reservation_id, image_name=image_name, count=node_count)

Note that this is a general outline, and you may need to modify the script further to match your specific requirements and the CHI@Edge environment. Additionally, you can refer to the CHI@Edge documentation and the Chameleon Cloud blog posts for more information on using CHI@Edge and container-based edge computing.

Further Reading
BlogCloud Wrangling Chameleons Python Library
DocsJupyter Python Chi
DocsGui
BlogConducting Research On The Edge Chiedge
DocsGetting Started

 |  | 0 | Keeps add_node_reservation + create_server — misses the conversion entirely. |
| P28 | Pitfall trap | S1 · Chatbot (artifact) | To convert your CHI@UC bare-metal script to run on CHI@Edge, you need to make the following changes:

Update the site: Change chi.use_site("CHI@UC") to chi.use_site("CHI@Edge").
Change the device type: Replace node_type='compute_skylake' with machine_name='raspberrypi4-64', as CHI@Edge uses Raspberry Pi 4 devices.
Use containers: CHI@Edge uses containers instead of bare-metal servers. You'll need to create a container using container.create_container() instead of create_server().
Specify the container image: Use the image parameter to specify the container image, such as image="ghcr.io/chameleoncloud/edge_ssh_image:latest".
Expose ports: Expose the necessary ports using the exposed_ports parameter, such as exposed_ports=[22].
Associate a floating IP: Use chi.container.associate_floating_ip() to associate a floating IP with the container.
Update the reservation: Update the reservation to use the machine_name and count parameters, such as lease.add_device_reservation(reservations, count=2, machine_name=machine_name).
Here's an example of the updated code:

chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")

machine_name = "raspberrypi4-64"
start, end = lease.lease_duration(days=1)
lease_name = f"ssh-{machine_name}-{start}"
reservations = []
lease.add_device_reservation(reservations, count=2, machine_name=machine_name)
container_lease = lease.create_lease(lease_name, reservations)
lease_id = container_lease["id"]
lease.wait_for_active(lease_id)

container_name = f"tutorial-{machine_name}-ssh".replace("_","-")
my_container = container.create_container(
    container_name,
    image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
    workdir="/home",
    exposed_ports=[22],
    reservation_id=lease.get_device_reservation(lease_id),
    platform_version=2,
)

# ... (rest of the code remains the same)

Note that this is just an example, and you may need to modify the code further to suit your specific use case. Additionally, make sure to update the edge_user_public_key file with your actual RSA public key before running the script.

Further Reading
DocsGui
BlogChi In A Box Update
DocsFederation
DocsGetting Started
BlogSeamless Ssh Container Access With Chiedge
BlogBack To School With Chameleon

 |  | 2 | Correct conversion to add_device_reservation + create_container. |
| P28 | Pitfall trap | S2 · GPT (blind) | Need the actual script to do a precise conversion.

In the meantime, here’s the core mapping from CHI@UC bare-metal (Lease + Reservation + create_server) to CHI@Edge so you can translate it directly.

1. What changes between CHI@UC and CHI@Edge
Compute / node types
compute_skylake (UC bare metal cluster)
→ usually not available on Edge
CHI@Edge uses edge flavors, often:
baremetal is replaced with edge.small, edge.medium, etc.
or OpenStack flavor instead of node reservation types

So:

node_type='compute_skylake'

becomes something like:

flavor='edge.small'
2. Reservation model change
CHI@UC (what you have)

Typical flow:

add_node_reservation(node_type='compute_skylake', count=1)
CHI@Edge equivalent

CHI@Edge generally avoids explicit node-type reservations.

Instead:

You either skip reservation entirely
or use a lease with generic resource class

So you replace:

add_node_reservation(...)

with either:

nothing (if using on-demand edge nodes)
or a generic lease request (if required by your project setup)
3. Server creation change
CHI@UC
create_server(reservation_id=..., image=..., ...)
CHI@Edge

You switch to OpenStack-style scheduling:

create_server(
    name="edge-node",
    image_name="...",
    flavor="edge.small",
    network_name="shared-net"
)

Key differences:

❌ no reservation_id
❌ no node_type
✅ uses flavor
✅ uses standard network (often shared-net or external)
4. Side-by-side transformation pattern
Before (CHI@UC)
lease = add_node_reservation(node_type='compute_skylake', count=1)

server = create_server(
    reservation_id=lease['id'],
    image='CC-Ubuntu22.04',
    name='test-node'
)
After (CHI@Edge)
server = create_server(
    name='test-node',
    image_name='CC-Ubuntu22.04',
    flavor='edge.small',
    network_name='shared-net'
)
5. If your script uses full lease orchestration

Then the real simplification is:

CHI@UC	CHI@Edge
lease + reservation	usually none
node_type	flavor
add_node_reservation	removed
create_server(reservation_id=...)	create_server(flavor=...)
6. What I need from you for exact conversion

Paste:

your full CHI@UC script
or at least the lease + server section

Then I can rewrite it line-by-line for CHI@Edge without guessing flavors or network names. |  | 0 | Invents 'edge.small' flavors; keeps create_server; wrong model. |
| P28 | Pitfall trap | S2 · GPT (artifact) | Below is the direct translation of your CHI@UC bare-metal workflow (Skylake + compute node + server creation) into the CHI@Edge functional python-chi model, aligned with the artifact you provided.

The key shift is structural:

CHI@UC → add_node_reservation(... node_type='compute_skylake') + create_server
CHI@Edge → add_device_reservation(... machine_name='raspberrypi4-64') + create_container

No VMs. No OpenStack servers. Only container-on-device via lease.

CHI@Edge Equivalent of CHI@UC Bare-Metal Script
1. Environment setup (same pattern)
import chi
from chi import lease
from chi import container

chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")
2. Replace node reservation (UC → Edge mapping)
CHI@UC (conceptually)
add_node_reservation(node_type="compute_skylake")
CHI@Edge equivalent
add_device_reservation(machine_name="raspberrypi4-64")
machine_name = "raspberrypi4-64"

start, end = lease.lease_duration(days=1)
lease_name = f"edge-ssh-{machine_name}-{start}"

reservations = []

lease.add_device_reservation(
    reservations,
    count=2,                 # preserved behavior from artifact
    machine_name=machine_name
)

edge_lease = lease.create_lease(lease_name, reservations)
lease_id = edge_lease["id"]

lease.wait_for_active(lease_id)

What changed vs UC:

No node_type
No bare-metal host allocation
You are reserving edge devices, not servers
3. Replace server creation (UC → container creation)
CHI@UC equivalent
create_server(...) → boots VM on Skylake
CHI@Edge equivalent
container.create_container(...) → runs on reserved Raspberry Pi 4
container_name = f"edge-container-{machine_name}".replace("_", "-")

edge_container = container.create_container(
    container_name,
    image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
    workdir="/home",
    exposed_ports=[22],
    reservation_id=lease.get_device_reservation(lease_id),
    platform_version=2,
)

Mapping:

CHI@UC	CHI@Edge
compute_skylake node	raspberrypi4-64 device
create_server	create_container
VM instance	container
OpenStack networking	floating IP attach
4. SSH key injection (same pattern, unchanged logic)
container_uuid = edge_container.uuid

chi.container.upload(
    container_uuid,
    "./edge_user_public_key",
    "/root/.ssh/"
)

chi.container.execute(
    container_uuid,
    '/bin/bash -c "chmod 600 /root/.ssh/authorized_keys"'
)

chi.container.execute(
    container_uuid,
    '/bin/bash -c "cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys"'
)

Critical constraint preserved:

edge_user_public_key must contain a single-line RSA public key
5. Networking (UC floating IP → Edge floating IP association)
ip_address = chi.container.associate_floating_ip(container_uuid)

print("SSH command:")
print(f"ssh root@{ip_address}")

Difference vs CHI@UC:

No security groups
No VM port rules
Edge runtime exposes port 22 directly via container config
6. Cleanup (same conceptual role)
chi.container.destroy_container(container_uuid)

And implicitly:

lease expiration removes device reservation
Full CHI@Edge “UC-style script” (compact version)

This is the direct structural equivalent of a typical CHI@UC workflow:

import chi
from chi import lease, container

chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")

machine_name = "raspberrypi4-64"

start, end = lease.lease_duration(days=1)
reservations = []

lease.add_device_reservation(reservations, count=2, machine_name=machine_name)
edge_lease = lease.create_lease(f"edge-{machine_name}-{start}", reservations)
lease_id = edge_lease["id"]

lease.wait_for_active(lease_id)

edge_container = container.create_container(
    f"edge-container-{machine_name}",
    image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
    workdir="/home",
    exposed_ports=[22],
    reservation_id=lease.get_device_reservation(lease_id),
    platform_version=2,
)

container_uuid = edge_container.uuid

chi.container.upload(container_uuid, "./edge_user_public_key", "/root/.ssh/")
chi.container.execute(container_uuid, '/bin/bash -c "chmod 600 /root/.ssh/authorized_keys"')
chi.container.execute(container_uuid, '/bin/bash -c "cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys"')

ip = chi.container.associate_floating_ip(container_uuid)
print(f"ssh root@{ip}")

# cleanup when done
# chi.container.destroy_container(container_uuid)
Key conceptual shift (important)

If you only remember one thing:

CHI@UC = allocate machines → boot VMs → create servers
CHI@Edge = allocate devices → run containers directly on hardware

So your transformation rule is:

add_node_reservation + create_server
→ add_device_reservation + create_container

If you want, the next step is mapping your exact CHI@UC Skylake script line-by-line, not just conceptually. |  | 2 | Excellent UC→Edge mapping table + full converted script. |
| P28 | Pitfall trap | S3 · Claude (blind) | I don't see an uploaded script — could you paste it (or upload the file) so I can do an exact conversion rather than a generic template?
That said, here are the three core changes you'll need, so you can start while I wait:
1. Site
python# Before
chi.set('site', 'CHI@UC')

# After
chi.set('site', 'CHI@Edge')
2. Reservation — nodes → devices
python# Before
lease.add_node_reservation(reservations, node_type='compute_skylake', count=1)
reservation_id = lease.get_node_reservation(my_lease['id'])

# After  (pick one filter that matches your target hardware)
lease.add_device_reservation(reservations, count=1, machine_name='raspberrypi4-64')
# or filter by model:  machine_model='Raspberry Pi 4 Model B'
reservation_id = lease.get_device_reservation(my_lease['id'])
Available machine_name values you can query with:
pythonfrom chi import hardware
hardware.get_nodes(site='CHI@Edge')   # lists edge device types
3. Server → Container

CHI@Edge doesn't provision VMs — it deploys Docker containers via chi.container:
python# Before
from chi import server
my_server = server.create_server('my-server', reservation_id=reservation_id,
                                  image_name='CC-Ubuntu20.04')
server.wait_for_active(my_server.id)

# After
from chi import container
my_container = container.create_container(
    'my-container',
    image='ubuntu:20.04',           # any Docker Hub / registry image
    reservation_id=reservation_id,
    device_profiles=['pi4'],        # optional: hardware capability hints
    exposed_ports=[22],             # optional
    environment={'MY_VAR': 'val'},  # optional
)
container.wait_for_active(my_container['uuid'])
Full skeleton after conversion:
pythonimport chi
from chi import lease, container

chi.set('project_name', 'YOUR_PROJECT')
chi.set('site', 'CHI@Edge')

# 1. Lease
reservations = []
lease.add_device_reservation(reservations, count=1, machine_name='raspberrypi4-64')
start, end = lease.lease_duration(days=1)
my_lease = lease.create_lease('my-edge-lease', reservations,
                               start_date=start, end_date=end)
lease.wait_for_active(my_lease['id'])

# 2. Container (replaces create_server)
reservation_id = lease.get_device_reservation(my_lease['id'])
my_container = container.create_container(
    'my-edge-container',
    image='ubuntu:20.04',
    reservation_id=reservation_id,
)
container.wait_for_active(my_container['uuid'])

# 3. Use it
container.execute(my_container['uuid'], 'echo hello from the edge')

# 4. Cleanup
container.destroy_container(my_container['uuid'])
lease.delete_lease(my_lease['id'])
Paste your actual script and I'll do a line-for-line conversion preserving your logic, variable names, and any networking/floating-IP setup. |  | 1 | Right conversion shape; invents device_profiles=['pi4'] and machine_model field. |
| P28 | Pitfall trap | S3 · Claude (artifact) | Here's the mapping from CHI@UC bare-metal to CHI@Edge, followed by a converted script:
Key conceptual shifts:
CHI@UC (bare-metal)CHI@Edge (containers)chi.use_site("CHI@UC")chi.use_site("CHI@Edge")lease.add_node_reservation(...)lease.add_device_reservation(...)node_type='compute_skylake'machine_name='raspberrypi4-64'chi.server.create_server(...)container.create_container(...)Boots a VM/bare-metal OS imagePulls a container imageFloating IP via Novachi.container.associate_floating_ip(uuid)

pythonimport chi
from chi import container, lease

# ── 1. Site & project ────────────────────────────────────────────────────────
chi.use_site("CHI@Edge")           # was: chi.use_site("CHI@UC")
chi.set("project_name", "Chameleon")

# ── 2. Lease ─────────────────────────────────────────────────────────────────
machine_name = "raspberrypi4-64"   # was: node_type='compute_skylake'
start, end = lease.lease_duration(days=1)
lease_name = f"ssh-{machine_name}-{start}"

reservations = []
lease.add_device_reservation(       # was: lease.add_node_reservation(...)
    reservations,
    count=2,
    machine_name=machine_name,      # was: node_type='compute_skylake'
)

container_lease = lease.create_lease(lease_name, reservations)
lease_id = container_lease["id"]

print(f"Waiting for lease {lease_name} ({lease_id}) to become active...")
lease.wait_for_active(lease_id)
print("Lease active.")

# ── 3. Create container ───────────────────────────────────────────────────────
# CHI@Edge uses Kubernetes — no underscores in names
container_name = f"tutorial-{machine_name}-ssh".replace("_", "-")

try:
    my_container = container.create_container(   # was: chi.server.create_server(...)
        container_name,
        image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
        workdir="/home",
        exposed_ports=[22],
        reservation_id=lease.get_device_reservation(lease_id),
        platform_version=2,
    )
except RuntimeError as ex:
    print(ex)
    print(f"Stop/delete {container_name} and retry.")
else:
    print(f"Container created: {container_name}")

# ── 4. Inject SSH key ─────────────────────────────────────────────────────────
# Replace edge_user_public_key with a file containing your one-line RSA pubkey
chi.container.upload(my_container.uuid, "./edge_user_public_key", "/root/.ssh/")
chi.container.execute(my_container.uuid, '/bin/bash -c "chmod 600 /root/.ssh/authorized_keys"')
chi.container.execute(my_container.uuid, '/bin/bash -c "cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys"')

# ── 5. Floating IP ────────────────────────────────────────────────────────────
ip = chi.container.associate_floating_ip(my_container.uuid)  # was: chi.server.associate_floating_ip(...)
print(f"Connect with: ssh root@{ip}")

# ── 6. Cleanup ────────────────────────────────────────────────────────────────
# chi.container.destroy_container(my_container.uuid)

A few gotchas to watch for:

count=2 quirk — the artifact reserves two devices but only the first reservation is consumed by get_device_reservation(lease_id). This is intentional (keeps a spare) but means you're paying for two devices.
No underscores in container names — Kubernetes rejects them; the .replace("_","-") handles it.
Key file — create ./edge_user_public_key with your actual single-line RSA public key before running the upload cell. The repo's placeholder is literally the string replace this line with your RSA public key.
Hung SSH connection — if ssh root@<ip> hangs, release the floating IP from the CHI@Edge OpenStack dashboard and re-run the associate_floating_ip cell.
 |  | 2 | Cleanest diff table; correct full conversion. |
## Sheet: Summary
|  | Results summary |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  | Auto-computed from the Outputs sheet as you grade. Mean score (0–2) and % of max per setup. |  |  |  |  |  |  |
|  | Model versions tested (fill in) |  |  |  |  |  |  |
|  | S1 — Chatbot build / date: |  |  |  |  |  |  |
|  | S2 — GPT model: |  |  |  |  |  |  |
|  | S3 — Claude model + setting: |  |  |  |  |  |  |
|  | Metric | S1 · Chatbot (blind) | S1 · Chatbot (artifact) | S2 · GPT (blind) | S2 · GPT (artifact) | S3 · Claude (blind) | S3 · Claude (artifact) |
|  | Mean score (0–2) | 0.214285714285714 | 1.64285714285714 | 0.142857142857143 | 2 | 0.428571428571429 | 2 |
|  | % of max | 10.7142857142857 | 82.1428571428571 | 7.14285714285714 | 100 | 21.4285714285714 | 100 |
|  | Runs graded (of 28) | 14 | 14 | 14 | 14 | 14 | 14 |
|  | Headline: blind → artifact lift |  |  |  |  |  |  |
|  | Chatbot lift (pp) | 71.4285714285714 |  |  |  |  |  |
|  | GPT lift (pp) | 92.8571428571429 |  |  |  |  |  |
|  | Claude lift (pp) | 78.5714285714286 |  |  |  |  |  |
|  | Mean score by category × setup |  |  |  |  |  |  |
|  | Category | S1 blind | S1 art | GPT blind | GPT art | Cla blind | Cla art |
|  | Setup | 2 | 2 | 1 | 2 | 2 | 2 |
|  | Reservation | 0 | 1.66666666666667 | 0 | 2 | 0 | 2 |
|  | Container | 0.166666666666667 | 1.83333333333333 | 0.166666666666667 | 2 | 0.333333333333333 | 2 |
|  | SSH / Dev | 0 | 1 | 0 | 2 | 0.5 | 2 |
|  | Peripherals · Camera | — | — | — | — | — | — |
|  | Peripherals · Sense HAT | — | — | — | — | — | — |
|  | Availability | 0 | 1 | 0 | 2 | 0 | 2 |
|  | Pitfall trap | 0 | 2 | 0 | 2 | 1 | 2 |