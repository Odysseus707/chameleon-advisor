# edge-picamera-image — Pi Camera Module 3 on CHI@Edge

**Source artifact:** `edge-picamera-image` · **Built from:** `picamera_tutorial.ipynb` (single notebook)
**python-chi style:** object-oriented (`context.choose_site`, `lease.Lease`, `container.Container`)

## What it does
Reserves a Raspberry Pi 4 that has a Pi Camera Module 3 attached, launches a container carrying the `libcamera` + `rpicam-apps` + `picamera2` stack (enabled by the **`pi_libcamera`** device profile), then captures media three ways:
1. a 1920×1080 still PNG via the `rpicam-still` CLI,
2. the same still via the `picamera2` Python library (`camera_test.py`),
3. a 5-second 1080p H264 video via `rpicam-vid`,

downloading each result back with `container.download()`.

End-to-end flow: site/project setup → find `iot-rpi4-picam*` devices → 3-hour lease → launch container (`pi_libcamera`) → `rpicam-hello` camera check → still capture (CLI + picamera2) → video capture → cleanup.

## Exact reference values
| Item | Value |
|---|---|
| Site/project | `context.choose_site(default="CHI@Edge")`, `context.choose_project()` |
| device_type | `"raspberrypi4-64"` (in `hardware.get_devices(device_type=...)`) |
| device_name(s) | filtered by `d.device_name.startswith("iot-rpi4-picam")`, uses `picamera_devs[0]`; commented alt `device_name='iot-rpi4-picam2'` |
| device_profiles | `["pi_libcamera"]` |
| Container image | `image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest"` |
| Exposed ports | `exposed_ports=[]` |
| Container command | `command=["sleep", "infinity"]` |
| Lease duration | `lease.Lease("rpi4-camera-lease", duration=timedelta(hours=3))` |
| Helper script | `camera_test.py` (uploaded to `/app/`, run with `python3 camera_test.py`) |

## CLI commands run in the container (verbatim)
```
rpicam-hello --nopreview --list-cameras
rpicam-still  --nopreview  --output /app/test1.png --width 1920 --height 1080
rpicam-vid --nopreview -t 5000 --output /app/video1.mp4 --width 1920 --height 1080 --framerate 24
```

## Key python-chi calls (in order)
```python
context.choose_site(default="CHI@Edge"); context.choose_project()
hardware.get_devices(filter_reserved=True, device_type="raspberrypi4-64")
my_lease = lease.Lease("rpi4-camera-lease", duration=timedelta(hours=3))
my_lease.add_device_reservation(devices=[picamera_devs[0]])
my_lease.submit(idempotent=True)
my_container = container.Container("rpi4-camera-test-01",
    image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest",
    exposed_ports=[], reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"], device_profiles=["pi_libcamera"])
my_container.submit()
my_container.execute(cmd)            # rpicam-hello / rpicam-still / rpicam-vid / python3 camera_test.py
my_container.upload(f"{cwd}/camera_test.py", "/app/")
my_container.download("/app/test1.png", ".")
my_container.delete(); my_lease.delete()
```

## Helper script (`camera_test.py`, from the artifact)
Uses `picamera2`: `Picamera2()` → `create_still_configuration(main={"size": (1920, 1080)})` → `configure` → `start()` → `capture_file("/app/test2.png")` → `close()`.

## Container image (Dockerfile summary)
`FROM debian:bookworm-20250630-slim` → add Raspberry Pi apt repo (key `82B129927FA3303E`) → install `python3-libcamera`, `python3-picamera2`, `libcamera-apps-lite` → `WORKDIR /app` → `CMD ["sleep", "infinity"]`. The `pi_libcamera` profile exposes the `/dev` nodes (`dma_heap`, `media[0:4]`, `v4l-subdev0`, `vchiq`, `vcsm-cma`, `video[10:16]`, `video[18:23]`, `video31`) and read-only `/run/udev`.

## Notes (preserved source quirks — not corrected)
> NOTE: `rpicam-vid` writes `--output /app/video1.mp4`, but the following cell downloads `/app/video1.h264`. The section title/text also says "30fps H264" while the command passes `--framerate 24`. Both are preserved verbatim.

## Crux
device `iot-rpi4-picam*` (from `device_type="raspberrypi4-64"`) + device_profiles `["pi_libcamera"]` + image `ghcr.io/chameleoncloud/edge-picamera-image:latest`
