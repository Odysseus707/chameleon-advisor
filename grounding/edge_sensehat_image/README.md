# edge_sensehat_image — Sensors & GPIO (Sense HAT) on CHI@Edge

**Benchmark scope: Part A (RPi Sense HAT) only.**

**Source artifact:** `edge_sensehat_image` · **Built from (MERGED):** `rpi_sense.ipynb` (Part A) + `waveshare_sense.ipynb` (Part B)
**python-chi style:** object-oriented in both (`chi.context.use_site`, `lease.Lease`, `container.Container`)

## What it does
Reads sensors over the Pi's I2C/GPIO interfaces using two different "sense hat" boards. The single container image `ghcr.io/chameleoncloud/edge_sensehat_image:latest` serves both:

- **Part A — Raspberry Pi Official Sense HAT** (`rpi_sense.ipynb`): uses the `sense_hat` Python library to read pressure/temperature/humidity, plus `i2cdetect -y 1`. Launched with the **`pi_sensehat`** device profile.
- **Part B — Waveshare Sense HAT (B)** (`waveshare_sense.ipynb`): uses `i2c-tools` + Adafruit CircuitPython (Blinka) libraries to read 5 sensors via scripts in the image's `/examples` dir. Launched with the **`pi_gpio`** device profile and environment-variable workarounds.

End-to-end flow (each part): shared auth → device lease (4-hour) → launch container (with the part's device profile/env) → read sensors (`i2cdetect`, library/script execution) → delete container + lease.

## Shared authentication
```python
chi.context.use_site("CHI@Edge")
chi.context.choose_project()   # comment out if running outside jupyterhub
```
> The two source notebooks had identical auth cells; merged into one in `main.ipynb` (only redundancy trimmed).

## Exact reference values
| Item | Part A — RPi Sense HAT | Part B — Waveshare Sense HAT (B) |
|---|---|---|
| machine_name / machine_type | `machine_name = "raspberrypi4-64"`, passed as `machine_type=machine_name` | same |
| device_name (active) | `"iot-rpi4-picam3"` | `"iot-rpi-cm4-02"` |
| device_name (commented alts) | `"iot-rpi4-picam2"`, `"iot-rpi-cm4-02"` | `"iot-rpi4-picam2"`, `"iot-rpi4-picam3"` |
| device_profiles | `["pi_sensehat"]` | `["pi_gpio"]` |
| Container image | `image_ref="ghcr.io/chameleoncloud/edge_sensehat_image:latest"` | same |
| Container name | `"edge-rpi-sensehat"` | `"edge-waveshare-sensehat"` |
| environment | `{}` (empty) | `{"RPI_LGPIO_REVISION": "0xd03140", "BLINKA_FORCECHIP": "BCM2XXX", "BLINKA_FORCEBOARD": "RASPBERRY_PI_CM4"}` |
| Container command | `command=["-c", "sleep infinity"]` | same |
| Exposed ports | *none specified* | *none specified* |
| Lease duration | `lease.Lease(name=lease_name, duration=lease.timedelta(hours=4))` | same |
| reservation | `add_device_reservation(amount=1, machine_type=machine_name, device_name=device_name)` | same |

## Key python-chi calls (both parts)
```python
chi.context.use_site("CHI@Edge"); chi.context.choose_project()
container_lease = lease.Lease(name=lease_name, duration=lease.timedelta(hours=4))
container_lease.add_device_reservation(amount=1, machine_type=machine_name, device_name=device_name)
container_lease.submit()
my_container = container.Container(name=container_name,
    image_ref="ghcr.io/chameleoncloud/edge_sensehat_image:latest",
    device_profiles=[...],            # ["pi_sensehat"] (A) or ["pi_gpio"] (B)
    environment=environment_vars,
    reservation_id=container_lease.device_reservations[0]["id"],
    command=["-c", "sleep infinity"])
my_container.submit()
my_container.execute("i2cdetect -y 1")
my_container.execute(f"python3 -c '{cmd_str}'")         # Part A: sense_hat library
my_container.execute(f"python3 {script_file}")          # Part B: examples/*.py
my_container.delete(); container_lease.delete()
```

## Sensor tasks
- **Part A** (`sense_hat` library): `get_pressure()`, `get_temperature_from_pressure()`, `get_humidity()`, `get_temperature_from_humidity()`.
- **Part B** (`examples/` scripts run inside the container, all Adafruit CircuitPython):
  - `examples/SHTC3_temp_and_humidity_sensor_test.py` — `adafruit_shtc3.SHTC3`
  - `examples/ADS1015_analog_to_digital_test.py` — `adafruit_ads1x15.ADS1015` (`address=0x48`)
  - `examples/ICM-20948_9-axis_sensor_test.py` — `adafruit_icm20x.ICM20948` (`address=0x68`)
  - `examples/LPS22HB_air_pressure_sensor_test.py` — `adafruit_lps2x.LPS22` (`address=0x5C`)
  - `examples/TCS34725_color_recognition_sensor_test.py` — `adafruit_tcs34725.TCS34725` (`address=0x29`)

## I2C addresses (from notebook markdown)
- **RPi Sense HAT:** `0x1c` LSM9DS1 (magnetometer), `0x39` TCS3400, `0x46` LED2472G / eeprom, `0x5c` LPS25H, `0x5f` HTS221, `0x6a` LSM9DS1 (accel/gyro).
- **Waveshare Sense HAT (B):** `0x48` ADS1015, `0x68` ICM-20948, `0x5C` LPS22HB, `0x70` SHTC3, `0x29` TCS34725.

## Container image (Dockerfile summary)
Multi-stage `python:3.13-slim-bookworm`: (1) *rpi-sense-builder* builds `RTIMULib` + `sense-hat` wheels; (2) *waveshare-sense-builder* builds `lg`/`lgpio`/`rpi-lgpio`/`sysv_ipc`/`adafruit-blinka`/`adafruit-circuitpython-{ads1x15,icm20x,lps2x,shtc3,tcs34725}` wheels; (3) *output* installs `i2c-tools` + `gpiod`, the built wheels, and copies `examples/` to `/app/examples`. Profiles: `pi_sensehat` exposes `/dev/i2c-0`,`/dev/i2c-1`,`/dev/gpiomem`,`/dev/gpiochip0`,`/dev/gpiochip1`,`/dev/fb0`,`/dev/input/event0..2`; `pi_gpio` exposes `/dev/i2c-0`,`/dev/i2c-1`,`/dev/gpiomem`,`/dev/gpiochip0`,`/dev/gpiochip1`.

## Notes (preserved source quirks — not corrected)
> NOTE: In `waveshare_sense.ipynb` the markdown names the image `soufianejounaid/chi_edge_sensehat:latest`, but the code cell launches `ghcr.io/chameleoncloud/edge_sensehat_image:latest`. The crux/table above use the value the code actually runs.

> NOTE: The waveshare markdown discusses revision `0xd03115` (8 GB Pi 4), while the code sets `RPI_LGPIO_REVISION=0xd03140`. Preserved verbatim.

> NOTE: For the RPi Sense HAT the active `device_name` is `"iot-rpi4-picam3"` — the `picam` naming is inherited from device enrollment and is preserved verbatim.

## Crux
- **Part A:** device `iot-rpi4-picam3` (machine_type `raspberrypi4-64`) + device_profiles `["pi_sensehat"]` + image `ghcr.io/chameleoncloud/edge_sensehat_image:latest`
- **Part B:** device `iot-rpi-cm4-02` (machine_type `raspberrypi4-64`) + device_profiles `["pi_gpio"]` + image `ghcr.io/chameleoncloud/edge_sensehat_image:latest`
