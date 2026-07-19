# Peripheral showcase: Pi Camera Module 3 in CHI@Edge

Welcome to this Jupyter notebook guide on using the Camera on Raspberry Pis in CHI@Edge. This artifact will walk you through the steps to access and utilize the camera for your edge computing experiments.

**Important Note:** This notebook will work with any camera module, but only for devices that are set up to use the "libcamera" drivers. As of July 2025, all devices in CHI@Edge are configured this way.

In the following example we'll show how to use the Pi Camera Module 3 on a Raspberry Pi 4 to capture both a png image and an h264 30 fps video.

> **Grounding note.** Built from the single source notebook `picamera_tutorial.ipynb`. Code and exact strings preserved verbatim; stale outputs omitted. Uses the **object-oriented** python-chi style (`lease.Lease()`, `container.Container()`).
>
> **Crux:** device(s) `iot-rpi4-picam*` (filtered from `device_type="raspberrypi4-64"`) · device_profiles `["pi_libcamera"]` · image `ghcr.io/chameleoncloud/edge-picamera-image:latest` · exposed_ports `[]`.

```python
from chi import context

context.choose_site(default="CHI@Edge")
context.choose_project()
```

## Creating the Lease

To access the camera, we need to make a lease for the specific device that the camera is currently attached to. As of July 2025, we're still implementing the autodetection of this, but the below devices will have it attached.

```python
from chi import hardware

device_type = "raspberrypi4-64"
available_devices = hardware.get_devices(filter_reserved=True, device_type=device_type)

picamera_devs = [d for d in available_devices if d.device_name.startswith("iot-rpi4-picam")]
display([d.device_name for d in picamera_devs])
```

And then make a lease for one of them.

```python
from chi import lease
from datetime import timedelta

my_lease = lease.Lease("rpi4-camera-lease", duration=timedelta(hours=3))

my_lease.add_device_reservation(devices=[picamera_devs[0]])  # we're just getting a list of 1 device
# my_lease.add_device_reservation(device_name='iot-rpi4-picam2',amount=1) # or a specific one!
my_lease.submit(idempotent=True)
```

## Launching a container with libcamera and the rpicam apps

To take pictures and videos with the camera, we need to launch a container image with all the following pre-requisites:

- pi_libcamera device profile: a flag to expose all the necessary /dev devices required for the camera support
- libcamera: A complex camera stack designed to support all kinds of cameras on Linux.
- rpicam-apps: A set of example applications demonstrating how to use libcamera on Raspberry Pi.

We provide a prebuilt container image with these dependencies: ```ghcr.io/chameleoncloud/edge-picamera-image:latest```. For reprodcibility and customization, the Dockerfile for the image can be found in the same repo as this notebook.

Below, we will launch a long-running container doing more or less "nothing" so that it stays running, and then execute commands interactively.

```python
from chi import container

my_container = container.Container(
    "rpi4-camera-test-01",
    image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    command=["sleep", "infinity"],
    device_profiles=["pi_libcamera"],
)
my_container.submit()
```

## Verifying that the camera and drivers work

First, lets run a simple command to see if libcamera finds our camera. If the container started with the pi_libcamera device profile, this *should* work, but there are always some edge cases.
This will also help identify the capabilities of the attached camera.

Note: We specify `--nopreview` since there's no display attached to the device.

```python
cmd = "rpicam-hello --nopreview --list-cameras"
result,code = my_container.execute(cmd)
print(result)
```

## Capturing a still 1920x1080 picture with the camera

To capture pictures, we use the rpicam applications ([code](https://github.com/raspberrypi/rpicam-apps)). We use ```rpicam-still```[(docs)](https://www.raspberrypi.com/documentation/computers/camera_software.html#rpicam-still) to capture a 1920x1080 still png using the camera. Please visit the rpicam-apps [documentation](https://www.raspberrypi.com/documentation/computers/camera_software.html#rpicam-apps) to learn how to use other utilities.

**Important notes**:

- Capturing frames can take some time. It is not instant.
- If you run into dma_heap allocation issues/failure to allocate capture buffers, please lower the quality/size of your image or use the png format. The error occurs because the device to which the camera is attached currently only allocates a very limited amount of 64MB of contiguous memory blocks (cma). Each still capture requires a cma buffer amount that is proportional to the size of the target picture. Development efforts are currently ongoing to allow the allocation of more CMA on boot time to allow for larger frames.

```python
cmd = "rpicam-still  --nopreview  --output /app/test1.png --width 1920 --height 1080"
result,code = my_container.execute(cmd)
print(result)
```

Download the captured image from the running container using our ```container.download()``` utility. (**Note**: it takes a slight moment for the jupyter directory navigation pane to refresh and show the downloaded file)

```python
my_container.download("/app/test1.png", ".")
from IPython.display import Image
Image("test1.png", height=640,width=480)
```

## Using the picamera2 library instead of cli

Now, insted of running the command interactively, we'll instead use the picamera2 library to do the same task.

The snippet below will copy a script into the container, execute it, then copy the captured image image back.

```python
# Need to get the path for the python script in jupyter
import os
cwd = os.getcwd()
my_container.upload(f"{cwd}/camera_test.py", "/app/")

# execute it
result,code = my_container.execute("python3 camera_test.py")
print(result)
```

```python
# copy the output image back
my_container.download("/app/test2.png", ".")
from IPython.display import Image
Image("test2.png", height=640,width=480)
```

## Capturing a 5 second 1080p 30fps H264 video with the camera

To capture an h264 video we use the ```rpicam-vid```[(docs)](https://www.raspberrypi.com/documentation/computers/camera_software.html#rpicam-vid) utility to capture a 5 second 1080p video at a framerate of 30 fps. To playback the video, please download the file through the jupyter interface and use a video playback utility such as ```vlc```.

**Note**: the ```container.download()``` utility is primarily meant for smaller size files. Please resort to other methods such as cloud storage or scp to download larger files.

```python
cmd = "rpicam-vid --nopreview -t 5000 --output /app/video1.mp4 --width 1920 --height 1080 --framerate 24"
result,code = my_container.execute(cmd)
print(result)
```

> NOTE: Source inconsistencies preserved verbatim — `rpicam-vid` writes `--output /app/video1.mp4`, but the next cell downloads `/app/video1.h264`. Likewise this section's title/text says "30fps H264" while the command passes `--framerate 24`.

```python
# and copy it back
my_container.download("/app/video1.h264", ".")
```

## Cleanup :)

```python
my_container.delete()
```

```python
my_lease.delete()
```

## Appendix — helper script `camera_test.py` (from the source artifact)

The *picamera2 library* cell above uploads this file into the container (`my_container.upload(f"{cwd}/camera_test.py", "/app/")`) and runs it with `python3 camera_test.py`. It is part of the source artifact, reproduced here verbatim for grounding (it is not an executable cell of the original notebook).

```python
import time

from picamera2 import Picamera2

picam2 = Picamera2()

camera_config = picam2.create_still_configuration(main={"size": (1920, 1080)})
picam2.configure(camera_config)

picam2.start()
time.sleep(2)

metadata = picam2.capture_file("/app/test2.png")
print(metadata)

picam2.close()
```
