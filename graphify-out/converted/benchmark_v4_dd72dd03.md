<!-- converted from benchmark_v4.xlsx -->

## Sheet: Items
| ID | Lineage | Category | Axis | Tier (matched) | Verification | Prompt (paste verbatim) | Designed trap | Trap tags | Target artifact | Fed (matched) | Fed (heldout) | # checkers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AV01 | new | Availability | READ | T1 | V1 | Print the device_name of every raspberrypi4-64 device on CHI@Edge that is free to reserve right now (one per line). | filter_reserved=False (or omitted) lists reserved devices too. | live_state | A2 | A2 |  | 1 |
| AV02 | new | Availability | READ | T1 | V1 | Print True if the device iot-rpi4-picam2 is free to reserve right now on CHI@Edge, otherwise print False. | Static answers; direction bug on filter_reserved. | live_state | A2 | A2 |  | 1 |
| AV03 | new | Availability | READ | T1 | V1 | Print a single integer: how many CHI@Edge devices are free to reserve right now, across all device types. | Counting all enrolled devices instead of free ones. | live_state | A2 | A2 |  | 1 |
| AV04 | new | Availability | READ | T4 | V1 | Print the device_name of every currently-free CHI@Edge device that supports the pi_sensehat device profile. | supported_device_profiles is not documented in the tutorials; guessing device names instead of filtering by profile. | live_state | A2 | A2, A3 |  | 2 |
| N01 | new | Multi-device | ACT | T2 | V0 | Reserve three raspberrypi4-64 devices on CHI@Edge for 6 hours in one lease, and launch an SSH-enabled container on the lease so I can log in as root. | Adapted count and duration; bare-metal substitution; SSH image. | bare_metal_api, magic_image | A1 | A1 |  | 11 |
| N02 | new | Peripherals · Camera | ACT | T2 | V0 | Record a 10-second 720p video at 30 fps from the Pi camera and download it to my machine. | All three rpicam-vid parameters adapted from the tutorial values. | magic_command | A2 | A2 | A1, A3, A6 | 6 |
| N03 | new | Peripherals · Camera | ACT | T2 | V0 | Give me a 12-hour lease on a camera-equipped Pi and capture a 640x480 still from it. | Duration and resolution adapted; peripheral discovery still required. | magic_profile, live_state, magic_command | A2 | A2 |  | 11 |
| N04 | new | Peripherals · GPIO | VALIDATE | T1 | V0 | The Waveshare Sense HAT (B) is attached to iot-rpi-cm4-02. Reserve that device and launch the sensor container configured so the GPIO libraries work despite the missing devicetree info inside containers; then list what's on the I2C bus. | Choosing pi_sensehat because 'Sense HAT' is in the name (the Waveshare variant needs pi_gpio + three env-var workarounds). | magic_profile, env_workaround | A3 | A3 | A1, A2 | 10 |
| N05 | new | GPU / LLM | ACT | T2 | V0 | I already have an active CHI@Edge lease named 'my-llm-lease' on a GPU-capable device. Launch an Ollama container on it with GPU support, exposing only the Ollama API port, and give it a public IP. | Missing runtime='nvidia'; wrong port; re-creating the lease. | gpu_runtime, existing_lease | A4 | A4 | A1, A2, A3 | 9 |
| N06 | new | API translation | VALIDATE | T1 | V0 | Our old tutorial script below uses the deprecated imperative python-chi style. Rewrite it using the current object-oriented API (lease.Lease / container.Container), keeping the behavior identical.

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
``` | Keeping create_lease/create_container; losing the 10-hour duration or reservation wiring in translation. | api_generation, reservation_wiring | A2 | A2 |  | 10 |
| N07 | new | Multi-device | ACT | T1 | V0 | Reserve two Raspberry Pi 4s in one CHI@Edge lease and start an SSH-enabled container on each of them. | One reservation but only one container; separate leases per device. | bare_metal_api, multi_container | A1 | A1 |  | 9 |
| N08 | new | Existing lease | ACT | T1 | V0 | My lease 'serve-edge-vr' is already active on a Raspberry Pi 5. Launch the Jupyter minimal-notebook container on it, give it a public IP, and show me how to find the notebook's token URL from the container logs. | Re-creating the lease; missing get_logs; wrong image/port. | existing_lease, magic_image | A5 | A5 | A1, A2, A3 | 8 |
| N09 | new | Composition | ACT | T3 | V0 | Reserve a camera-equipped Pi, start the camera container, and retrofit SSH access into it (port 22, my public key, root login) so a teammate can log in and run captures themselves. | Camera image has no sshd; must be installed at runtime (edge-cpu-inference pattern) while keeping the pi_libcamera profile. | composition, magic_profile, key_injection | A2, A6 | A2, A6 |  | 14 |
| N10 | new | Composition | ACT | T3 | V0 | The device iot-rpi4-picam3 has both a camera module and a Sense HAT attached. Reserve it and launch ONE container that can access both peripherals; then verify each (list cameras; probe the sensor bus). | device_profiles is a list and can carry both profiles; models tend to pick one profile or launch two containers. | composition, magic_profile | A2, A3 | A2, A3 |  | 10 |
| N11 | new | Composition | ACT | T3 | V0 | Reserve the Pi 5 named nyu-rpi5-03 for exactly 2 hours using python-chi (no Horizon GUI), then launch the Jupyter minimal-notebook container on it with port 8888 and a public IP. | The Pi-5 tutorial only shows GUI leasing; the python-chi device_name lease pattern must come from the camera artifact. | composition, device_pinning | A2, A5 | A2, A5 |  | 10 |
| N12 | new | Composition | ACT | T3 | V0 | Capture a photo with the Pi camera, then classify it with the quantized MobileNet TFLite model inside the same container. | Combining the camera stack (profile/image) with the inference tooling (tflite-runtime, model file) from a different artifact. | composition, magic_profile, magic_command | A2, A6 | A2, A6 |  | 9 |
| N13 | new | API translation | ACT | T1 | V0 | Our lab standardized on the classic imperative python-chi API. Using ONLY that style (module functions - no Lease/Container classes), reserve one Pi 4 for 10 hours starting now and launch python:3.9-slim on it with SSH installed and reachable from outside. | platform_version=2 is mandatory on create_container; OO habits leak in. | api_generation, platform_version | A6 | A6 | A2, A3 | 12 |
| N14 | new | Uncovered peripheral | REASON | T4 | V0 | I want to record audio from a USB microphone plugged into a CHI@Edge Raspberry Pi. Which device profile do I use and how do I set up the container? | No audio profile is documented anywhere; the correct behavior is discovery or honest abstention, not a fabricated profile string. | abstention, magic_profile |  | A1, A2, A3 |  | 3 |
| N15 | new | Uncovered specifics | READ | T3 | V0 | Reserve any free Raspberry Pi 5 on CHI@Edge by machine type for 3 hours. | No artifact states the Pi-5 machine_type string (the Pi-5 tutorial leases via GUI UIDs); asserting one is fabrication - discover it. | live_state, magic_machine_type | A5 | A2, A5 | A1, A2, A3 | 4 |
| N16 | new | GPU / LLM | REASON | T3 | V0 | Run GPU-accelerated inference on a Jetson-class device on CHI@Edge: reserve one and start a CUDA-capable container on it. | Jetson device_type strings are not in the fed tutorials; GPU access on edge needs runtime='nvidia', which only one artifact shows. | gpu_runtime, live_state | A4 | A2, A4 | A1, A2, A3 | 7 |
| N17 | new | Uncovered API | REASON | T4 | V0 | My CHI@Edge lease expires in an hour; extend it by 2 more hours from python-chi. | No artifact demonstrates lease extension; invented extend/renew methods are the failure mode. | abstention |  | A1, A2, A3 |  | 2 |
| N18 | new | Uncovered peripheral | REASON | T4 | V0 | Use a plain USB (UVC) webcam on a CHI@Edge Pi with OpenCV - what device profile and container setup do I need? | pi_libcamera covers the CSI camera stack, not UVC; no UVC profile is documented - fabricating one is the failure mode. | abstention, magic_profile |  | A1, A2, A3 |  | 3 |
| P01 | v3:P01 | Setup | ACT | T1 | V0 | Show the minimal python-chi setup to target CHI@Edge and select my project. | chi.use_site vs context; wrong site string; forgets project. | site_setup | A2 | A2 |  | 3 |
| P02 | v3:P02 | Reservation | ACT | T2 | V0 | Reserve one Raspberry Pi 4 on CHI@Edge for 2 hours. | Bare-metal add_node_reservation / node_type. | bare_metal_api | A3 | A3 |  | 7 |
| P03 | v3:P03 | Reservation | ACT | T1 | V0 | Reserve a Pi on CHI@Edge and get the reservation_id I'll pass to a container. | Never retrieves the id; wrong attribute. | reservation_wiring | A2 | A2 |  | 4 |
| P04 | v3:P04 | Reservation | ACT | T2 | V0 | Reserve 3 Raspberry Pis on CHI@Edge of the same type in one lease. | Node reservation; count mishandled. | bare_metal_api, count_handling | A3 | A3 |  | 6 |
| P05 | v3:P05 | Container | ACT | T1 | V0 | Launch a basic Ubuntu container on a reserved Pi on CHI@Edge. | create_server (VM) instead of a container. | wrong_container_api, k8s_naming | A2 | A2 |  | 6 |
| P06 | v3:P06 | Container | VALIDATE | T1 | V0 | My container on CHI@Edge exits immediately. Make it stay running so I can exec into it. | No long-running command given. | keepalive_command | A2 | A2 |  | 3 |
| P07 | v3:P07 | Container | ACT | T2 | V0 | Expose port 8080 on my CHI@edge container and give it a public IP. | exposed_ports string format; FIP omitted; nova idioms. | port_exposure, floating_ip | A1 | A1 |  | 3 |
| P08 | v3:P08 | Container | ACT | T1 | V0 | Run 'ls /app' inside the running container in CHI@Edge and capture the output. | Hallucinated exec API; ignores tuple return. | exec_api, return_shape | A2 | A2 |  | 3 |
| P09 | v3:P09 | Container | ACT | T1 | V0 | Upload model.pt into the CHI@Edge container, then download results.csv back out. | Invented up/download names. | file_transfer_api | A2 | A2 |  | 4 |
| P10 | v3:P10 | Container | ACT | T1 | V0 | Tear everything down: remove the CHI@Edge container and free the device. | Invented teardown; leaves the lease. | teardown | A2 | A2 |  | 1 |
| P11 | v3:P11 | SSH / Dev | ACT | T1 | V0 | Launch an SSH-enabled container on a reserved Pi and tell me how to connect. | Doesn't know edge_ssh_image; wrong port type. | magic_image, port_exposure, floating_ip | A1 | A1 | A2, A3 | 7 |
| P12 | v3:P12 | SSH / Dev | VALIDATE | T1 | V0 | Inject my public key so I can SSH in as root. | Wrong key path / mechanism. | key_injection | A1 | A1 |  | 5 |
| P13 | v3:P13 | SSH / Dev | VALIDATE | T1 | V0 | Which image and exposed port do I need for SSH on CHI@Edge? | Generic sshd build; misses prebuilt image. | magic_image | A1 | A1 | A2, A3 | 2 |
| P14 | v3:P14 | SSH / Dev | REASON | T1 | V0 | End-to-end: get me a Pi on CHI@Edge I can hit with VS Code Remote-SSH. | Drops a link in reserve->image->key->FIP chain. | bare_metal_api, magic_image, key_injection, floating_ip | A1 | A1 |  | 11 |
| P15 | v3:P15 | Peripherals · Camera | READ | T1 | V0 | Find which Pis have a camera attached and reserve one. | Can't filter by peripheral; guesses device. | live_state, peripheral_discovery | A2 | A2 |  | 4 |
| P16 | v3:P16 | Peripherals · Camera | VALIDATE | T1 | V0 | Launch a container with the Pi camera enabled. | Omits device_profiles; guesses the profile name. | magic_profile, magic_image, keepalive_command | A2 | A2 | A1, A3 | 8 |
| P17 | v3:P17 | Peripherals · Camera | ACT | T1 | V0 | Capture a 1080p still from the Pi Camera and download it. | Made-up capture API; no download. | magic_command | A2 | A2 | A1, A3 | 5 |
| P18 | v3:P18 | Peripherals · Camera | ACT | T1 | V0 | Record a 5-second 1080p video from the camera. | Wrong tool / flags. | magic_command | A2 | A2 |  | 4 |
| P19 | v3:P19 | Peripherals · Camera | VALIDATE | T1 | V0 | Verify the camera is detected inside the container. | Invents a detection command. | magic_command | A2 | A2 |  | 3 |
| P20 | v3:P20 | Peripherals · Sense HAT | ACT | T1 | V0 | Reserve the specific device that has the Sense HAT attached. | Reserves any device; ignores device_name. | device_pinning | A3 | A3 |  | 5 |
| P21 | v3:P21 | Peripherals · Sense HAT | VALIDATE | T1 | V0 | Launch a container with the Sense HAT enabled. | Omits / guesses the device profile. | magic_profile, magic_image | A3 | A3 | A1, A2 | 8 |
| P22 | v3:P22 | Peripherals · Sense HAT | ACT | T1 | V0 | Read temperature, humidity and pressure from the Sense HAT. | Assumes host access; wrong library. | peripheral_library | A3 | A3 | A1, A2 | 3 |
| P23 | v3:P23 | Peripherals · Sense HAT | VALIDATE | T1 | V0 | From inside the container, list the I2C addresses to debug the sensor bus. | No I2C access path. | magic_command | A3 | A3 |  | 2 |
| P24 | v3:P24 | Peripherals · Sense HAT | VALIDATE | T1 | V0 | Which device profile and image do I use for Sense HAT / GPIO work? | Guesses the profile string. | magic_profile, magic_image | A3 | A3 | A1, A2 | 2 |
| P25 | v3:P25 | Availability | READ | T1 | V0 | List which CHI@Edge device types currently exist and are reservable. | Lists bare-metal flavors; invents an endpoint. | live_state | A2 | A2 |  | 2 |
| P26 | v3:P26 | Availability | READ | T1 | V0 | Before reserving on CHI@Edge, check whether a given device is free right now. | Claims it has no live state; fabricates an API. | live_state | A2 | A2 |  | 2 |
| P27 | v3:P27 | Availability | READ | T4 | V0 | How do I find which device_profiles a device supports? | Guesses a call. | live_state, magic_profile | A2 | A2 |  | 2 |
| P28 | v3:P28 | Pitfall trap | VALIDATE | T1 | V0 | Convert my CHI@UC bare-metal script (add_node_reservation, node_type='compute_skylake', create_server) to run on CHI@Edge. | Keeps node/flavor/server. | bare_metal_api, wrong_container_api | A1 | A1 |  | 5 |
## Sheet: Output
| ID | Condition | System | Model output (paste here) | Checker verdict (harness) | Human 0-2 | Failure tag | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
## Sheet: RunMatrix
| ID | Condition | Fed artifacts | Computed tier |
| --- | --- | --- | --- |
| AV01 | blind |  | blind |
| AV01 | matched | A2 | T1 |
| AV02 | blind |  | blind |
| AV02 | matched | A2 | T1 |
| AV03 | blind |  | blind |
| AV03 | matched | A2 | T1 |
| AV04 | blind |  | blind |
| AV04 | matched | A2, A3 | T4 |
| N01 | blind |  | blind |
| N01 | matched | A1 | T2 |
| N02 | blind |  | blind |
| N02 | matched | A2 | T2 |
| N02 | heldout | A1, A3, A6 | T4 |
| N03 | blind |  | blind |
| N03 | matched | A2 | T2 |
| N04 | blind |  | blind |
| N04 | matched | A3 | T1 |
| N04 | heldout | A1, A2 | T4 |
| N05 | blind |  | blind |
| N05 | matched | A4 | T2 |
| N05 | heldout | A1, A2, A3 | T4 |
| N06 | blind |  | blind |
| N06 | matched | A2 | T1 |
| N07 | blind |  | blind |
| N07 | matched | A1 | T1 |
| N08 | blind |  | blind |
| N08 | matched | A5 | T1 |
| N08 | heldout | A1, A2, A3 | T4 |
| N09 | blind |  | blind |
| N09 | matched | A2, A6 | T3 |
| N10 | blind |  | blind |
| N10 | matched | A2, A3 | T3 |
| N11 | blind |  | blind |
| N11 | matched | A2, A5 | T3 |
| N12 | blind |  | blind |
| N12 | matched | A2, A6 | T3 |
| N13 | blind |  | blind |
| N13 | matched | A6 | T1 |
| N13 | heldout | A2, A3 | T4 |
| N14 | blind |  | blind |
| N14 | uncovered | A1, A2, A3 | T4 |
| N15 | blind |  | blind |
| N15 | matched | A2, A5 | T3 |
| N15 | heldout | A1, A2, A3 | T4 |
| N16 | blind |  | blind |
| N16 | matched | A2, A4 | T3 |
| N16 | heldout | A1, A2, A3 | T4 |
| N17 | blind |  | blind |
| N17 | uncovered | A1, A2, A3 | T4 |
| N18 | blind |  | blind |
| N18 | uncovered | A1, A2, A3 | T4 |
| P01 | blind |  | blind |
| P01 | matched | A2 | T1 |
| P02 | blind |  | blind |
| P02 | matched | A3 | T2 |
| P03 | blind |  | blind |
| P03 | matched | A2 | T1 |
| P04 | blind |  | blind |
| P04 | matched | A3 | T2 |
| P05 | blind |  | blind |
| P05 | matched | A2 | T1 |
| P06 | blind |  | blind |
| P06 | matched | A2 | T1 |
| P07 | blind |  | blind |
| P07 | matched | A1 | T2 |
| P08 | blind |  | blind |
| P08 | matched | A2 | T1 |
| P09 | blind |  | blind |
| P09 | matched | A2 | T1 |
| P10 | blind |  | blind |
| P10 | matched | A2 | T1 |
| P11 | blind |  | blind |
| P11 | matched | A1 | T1 |
| P11 | heldout | A2, A3 | T4 |
| P12 | blind |  | blind |
| P12 | matched | A1 | T1 |
| P13 | blind |  | blind |
| P13 | matched | A1 | T1 |
| P13 | heldout | A2, A3 | T4 |
| P14 | blind |  | blind |
| P14 | matched | A1 | T1 |
| P15 | blind |  | blind |
| P15 | matched | A2 | T1 |
| P16 | blind |  | blind |
| P16 | matched | A2 | T1 |
| P16 | heldout | A1, A3 | T4 |
| P17 | blind |  | blind |
| P17 | matched | A2 | T1 |
| P17 | heldout | A1, A3 | T4 |
| P18 | blind |  | blind |
| P18 | matched | A2 | T1 |
| P19 | blind |  | blind |
| P19 | matched | A2 | T1 |
| P20 | blind |  | blind |
| P20 | matched | A3 | T1 |
| P21 | blind |  | blind |
| P21 | matched | A3 | T1 |
| P21 | heldout | A1, A2 | T4 |
| P22 | blind |  | blind |
| P22 | matched | A3 | T1 |
| P22 | heldout | A1, A2 | T4 |
| P23 | blind |  | blind |
| P23 | matched | A3 | T1 |
| P24 | blind |  | blind |
| P24 | matched | A3 | T1 |
| P24 | heldout | A1, A2 | T4 |
| P25 | blind |  | blind |
| P25 | matched | A2 | T1 |
| P26 | blind |  | blind |
| P26 | matched | A2 | T1 |
| P27 | blind |  | blind |
| P27 | matched | A2 | T4 |
| P28 | blind |  | blind |
| P28 | matched | A1 | T1 |
## Sheet: Summary
|  | Results summary (auto-computes as the Output sheet is graded) |  |  |  |
| --- | --- | --- | --- | --- |
|  | Condition | Graded cells | Checker pass rate | Mean human 0-2 |
|  | blind | 0 |  |  |
|  | matched | 0 |  |  |
|  | heldout | 0 |  |  |
|  | uncovered | 0 |  |  |