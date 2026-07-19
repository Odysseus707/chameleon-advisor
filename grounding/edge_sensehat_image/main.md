# Peripheral showcase: Sensors in CHI@Edge

Welcome to this Jupyter notebook guide on using sesnors in CHI@Edge.

We currently have two types of "sense hats":
* [Raspberry Pi Sense Hat](https://www.raspberrypi.com/documentation/accessories/sense-hat.html)
* [Waveshare Sense Hat (B)](https://www.waveshare.com/wiki/Sense_HAT_(B))

These sense hats each package a 3 axis gyroscope, accelerometer, and magnetometer, as well as a variety of environmental sensors for temperature, pressure, and humidity.

This artifact will walk you through the steps to access and utilize a sense hat for your edge computing experiments, as well as the differences between the two types.

Please check out our extensive [documentation](https://chameleoncloud.gitbook.io/chi-edge/device-enrollment/peripherals-and-device-profiles) on how to add peripherals to CHI@Edge devices.

In the following example we'll show how to use the sense hat to capture sensor data.

This notebook will demonstrate the RPi sense hat, and [waveshare_sense.ipynb](waveshare_sense.ipynb) the waveshare sense hat.

> **Grounding note.** Merged from two source notebooks: `rpi_sense.ipynb` (**Part A** below) and `waveshare_sense.ipynb` (**Part B** below). Both notebooks had identical *Authenticate to CHI@Edge* site/project cells; that single redundant cell was merged into the shared auth section below — the only redundancy trimmed. All other code and exact strings are verbatim; stale outputs omitted. Both notebooks use the **object-oriented** python-chi style (`lease.Lease()`, `container.Container()`).
>
> **Crux (Part A — RPi Sense HAT):** device `iot-rpi4-picam3` (machine_type `raspberrypi4-64`) · device_profiles `["pi_sensehat"]` · image `ghcr.io/chameleoncloud/edge_sensehat_image:latest`.
>
> **Crux (Part B — Waveshare Sense HAT (B)):** device `iot-rpi-cm4-02` (machine_type `raspberrypi4-64`) · device_profiles `["pi_gpio"]` · image `ghcr.io/chameleoncloud/edge_sensehat_image:latest` · env `RPI_LGPIO_REVISION=0xd03140`, `BLINKA_FORCECHIP=BCM2XXX`, `BLINKA_FORCEBOARD=RASPBERRY_PI_CM4`.

## Authenticate to CHI@Edge

As with our other artifacts, python-chi has some helper methods to connect more easily when run from inside jupyterhub.

If you're running this artifacts somewhere else, such as on your laptop, please note the commented section!

```python
import chi

chi.context.use_site("CHI@Edge")
chi.context.choose_project() # comment this line if running outside of jupyterhub

# # If running this nodebook outside of chameleon's jupyterhub, uncomment this section and fill in your_project_name
# import openstack
# chi.set("project_domain_name", "chameleon")
# chi.set("project_name", "your_project_name")
# connection = openstack.connect(cloud="edge")
# chi.set("token", connection.auth_token)
```

# Part A — Raspberry Pi Official Sense Hat

> Source notebook: `rpi_sense.ipynb`

## Creating the Lease

To access the sense hat, we need to make a lease for a specific device that the camera is currently attached to.

> NOTE: For the RPi Sense HAT the active `device_name` is `iot-rpi4-picam3` (the source also lists commented alternatives `iot-rpi4-picam2` and `iot-rpi-cm4-02`). The `picam` naming is inherited from device enrollment and is preserved verbatim.

```python
from chi import lease
import os

# machine name refers to the "type" of device
machine_name = "raspberrypi4-64"

# Reserving the specific device to which the Sense Hat is attached
# Note: Soon, we'll have peripherals listed in the hardware browser, and reservable via blazar query, so you won't need to know the right name ahead of time

# device_name = "iot-rpi4-picam2" # RPI sense hat
device_name = "iot-rpi4-picam3" # RPI sense hat
# device_name = "iot-rpi-cm4-02" # waveshare sense hat

# make a unique name for the lease
username = os.environ.get("USER")
lease_name = f"{username}-{device_name}"
container_lease = lease.Lease(name=lease_name, duration=lease.timedelta(hours=4))
container_lease.add_device_reservation(
    amount=1, machine_type=machine_name, device_name=device_name
)
container_lease.submit()
print("Done!")
```

## Accessing sensors with sense_hat library
Raspberry Pi Provides a well documented library to interact with the sense hat, appropriatley named "sense_hat. See https://sense-hat.readthedocs.io/en/latest/

The following will launch a container with the needed libraries built in.

```python
from chi import container

# Set a name for the container. Because CHI@Edge uses Kubernetes, ensure that underscores aren't in the name
container_name = "edge-rpi-sensehat".replace("_", "-")

environment_vars = {}

my_container = container.Container(
    name=container_name,
    image_ref="ghcr.io/chameleoncloud/edge_sensehat_image:latest",
    device_profiles=["pi_sensehat"],
    environment=environment_vars,
    reservation_id=container_lease.device_reservations[0]["id"],
    command=["-c", "sleep infinity"],
)
my_container.submit()
```

### The RPI sense hat provides the following sensors:

* Pressure/temperature sensor: STMicro LPS25HB
  * 260 to 1260 hPa absolute pressure range
  * 24-bit pressure data output
  * 0 to +65°C accurate temperature measurement range (±2°C)
  * 16-bit temperature data output
* Humidity temperature sensor: STMicro HTS221
  * 0 to 100% relative humidity range
  * 15 to 40°C accurate temperature measurement range (±0.5°C)
  * 16-bit data output
*  IMU: STMicro LSM9DS1 Accelerometer/gyroscope/magnetometer
  * ±16g acceleration measurement range
  * ±16 gauss magnetometer measurement range
  * ±2000dps gyroscope measurement range
  * 16-bit resolution for each measurement channel
* Color sensor: TCS3400 RGB colour and brightness sensor
* LED matrix: 8×8 RGB LED display
* Joystick: 5-button miniature joystick with up, down, left, right, and middle-click

The following example will get readings from both the pressure and humidity sensors, (and temperature from both of them).

```python
cmd_str = """
from sense_hat import SenseHat

sense = SenseHat()
sense.clear()

# Returns the pressure in Millibars
pressure = sense.get_pressure()

# Returns the temperature in Celsius from the pressure sensor
temperature_pressure = sense.get_temperature_from_pressure()

# Returns the percentage of relative humidity
humidity = sense.get_humidity()

# Returns the temperature in Celsius from the humidity sensor
temperature_humidity = sense.get_temperature_from_humidity()

print(
    "Pressure: {:.1f} mbar, Temperature (from pres): {:.1f} C,  Relative Humidity: {:.1f} %, Temperature (from hum): {:.1f} C".format(
        pressure, temperature_pressure, humidity, temperature_humidity
    )
)
"""

# if you see '0' values, try running this again. The sensors may need to be initialized.

stdout,resultcode = my_container.execute(f"python3 -c '{cmd_str}'")
print(stdout)
```

## Debugging, and poking around at a lower level

The sense hat exposes most sensors over i2c, but the display will appear under `/dev/fb0`, and the joystick under `/dev/input`.
For the most part, RPI's [RTIMULib](https://github.com/RPi-Distro/RTIMULib) abstracts this for you, but you're free to poke around.


### Displaying the I2C sensor map and understanding the mapping of I2C device addresses to sensors
We use the ```i2cdetect``` command from the ```i2c-tools``` utility to display the current detected i2c devices. To understand the mapping of these addresses to the various sensors onboard the sense hat, we end up needing to look up datasheets for each sensor mentioned in [Raspberry Pi's datasheet for the sense hat](https://datasheets.raspberrypi.com/sense-hat/sense-hat-product-brief.pdf) and [top level documentation](https://www.raspberrypi.com/documentation/accessories/sense-hat.html)

### Sensor I2C device addresses

- LPS22HB: 0x5C # pressure sensor

- 0x1c: LSM9DS1  -- IMU (Magnetometer)
- 0x39: TCS3400  -- Color and Brightness
- 0x46: LED2472G -- shift register for LED Matrix
- 0x5c: LPS25H   -- Pressure/Temperature sensor
- 0x5f: HTS221   -- Humidity/Temperature sensor
- 0x6a: LSM9DS1  -- IMU (Accelerometer and Gyroscope)
- 0x46: eeprom for the sense hat

```python
# example showing detected i2c addresses
result, code = my_container.execute("i2cdetect -y 1")
print(result)
```

### Diving deeper

We won't get into the weeds with the Pi sense hat, but check out the [waveshare sense hat](waveshare_sense.ipynb) example for a lower level guide. *(In this merged notebook, that is **Part B** below.)*

## Cleaning up

```python
# delete the container so it doesn't hang around
my_container.delete()
```

```python
# deleting the lease will free up the device now, instead of waiting for it to expire later
container_lease.delete()
```

# Part B — Waveshare Sense Hat (B)

> Source notebook: `waveshare_sense.ipynb`
>
> NOTE: The source `waveshare_sense.ipynb` repeated the same *Authenticate to CHI@Edge* site/project cell shown at the top of this merged notebook; rerun it if you skipped Part A. Everything below is from `waveshare_sense.ipynb`.

# Peripheral showcase: Waveshare sense hat in CHI@Edge

Welcome to this Jupyter notebook guide on using the [Waveshare Sense Hat (B)](https://www.waveshare.com/wiki/Sense_HAT_(B)) within CHI@Edge, a sensor expansion board specially designed for Raspberry Pi that houses an onboard gyroscope, accelerometer, magnetometer, barometer, temperature and humidity sensor, etc.. This artifact will walk you through the steps to access and utilize the sense hat for your edge computing experiments..


In the following example we'll show how to use the sense hat to capture sensor data.

## Creating the Lease

To access the sense hat, we need to make a lease for a specific device that the camera is currently attached to.

```python
from chi import lease
import os

# machine name refers to the "type" of device
machine_name = "raspberrypi4-64"

# Reserving the specific device to which the Sense Hat is attached
# Note: Soon, we'll have peripherals listed in the hardware browser, and reservable via blazar query, so you won't need to know the right name ahead of time

# device_name = "iot-rpi4-picam2" # RPI sense hat
# device_name = "iot-rpi4-picam3" # RPI sense hat
device_name = "iot-rpi-cm4-02" # waveshare sense hat

# make a unique name for the lease
username = os.environ.get("USER")
lease_name = f"{username}-{device_name}"
container_lease = lease.Lease(name=lease_name, duration=lease.timedelta(hours=4))
container_lease.add_device_reservation(
    amount=1, machine_type=machine_name, device_name=device_name
)
container_lease.submit()
print("Done!")
```

## Launching a container with i2c-tools and adafruit

To detect the various sensors offered by the waveshare sense hat, we provide a container image ```soufianejounaid/chi_edge_sensehat:latest``` with all the following pre-requisites:

- pi_gpio device profile: a flag to expose all the necessary /dev devices required for the waveshare sense hat support
- i2c-tools: A set of I2C utilities for Linux, which includes tools to probe and interact with I2C devices connected to the system.
- libgpiod2: A library for interacting with the GPIO pins on the Raspberry Pi.
- gpiod: A command-line tool for controlling the GPIO pins using the libgpiod library.
- adafruit-blinka: A compatibility layer that allows the use of CircuitPython libraries on a Raspberry Pi, enabling the use of various sensor libraries.
- rpi-lgpio: A library for accessing the GPIO pins on the Raspberry Pi, used by the Adafruit Blinka library to interact with the hardware.

Beyond the above dependencies, the provided image contains a directory named ```/examples``` containing 5 python scripts demonstrating the usage of each of the waveshare sense hat's onboard sensors. The ```Dockerfile``` for this image as well as the code for the examples are also provided as part of this artifact and can be accessed from the directory tree within your jupyter environment.

**Important note** The ```RPI_LGPIO_REVISION``` environment variable here is necessary to indicate to the ```rpi-lgpio``` library that we are indeed running on a raspberry-pi platform. when using this library, it is important to find the revision number for the host device model that the container is running on ```cat /proc/cpuinfo```. In this case, the revision number ```0xd03115``` corresponds to the following raspberry pi 4 model:

```
Revision	Release Date	Model	PCB Revision	Memory  	Notes
d03115  	Q1 2022     	4 Model B           	1.5	8 GB	(Mfg by Sony)
```

To find what model pi the revision number under ```cat /proc/cpuinfo``` corresponds to, use the [Rpi Hardware history table provided by elinux.org](https://elinux.org/RPi_HardwareHistory).

> NOTE: Source inconsistencies preserved verbatim. The markdown above names the image `soufianejounaid/chi_edge_sensehat:latest`, but the code cell below actually launches `ghcr.io/chameleoncloud/edge_sensehat_image:latest`. The markdown also discusses revision `0xd03115` (8 GB Pi 4), while the code sets `RPI_LGPIO_REVISION=0xd03140`.

```python
from chi import container

# Set a name for the container. Because CHI@Edge uses Kubernetes, ensure that underscores aren't in the name
container_name = "edge-waveshare-sensehat".replace("_", "-")

# The following env vars are a workaround for /sys/firmware/devicetree/base not being availabile inside
# the containers, otherwise these libraries would auto-detect the correct device info.
# RPI_LGPIO_REVISION
# see https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#new-style-revision-codes

environment_vars = {
    "RPI_LGPIO_REVISION": "0xd03140",
    "BLINKA_FORCECHIP": "BCM2XXX",
    "BLINKA_FORCEBOARD": "RASPBERRY_PI_CM4",
}

my_container = container.Container(
    name=container_name,
    image_ref="ghcr.io/chameleoncloud/edge_sensehat_image:latest",
    device_profiles=["pi_gpio"],
    environment=environment_vars,
    reservation_id=container_lease.device_reservations[0]["id"],
    command=["-c", "sleep infinity"],
)
my_container.submit()
```

## Displaying the I2C sensor map and understanding the mapping of I2C device addresses to sensors
We use the ```i2cdetect``` command from the ```i2c-tools``` utility to display the current detected i2c devices. To understand the mapping of these addresses to the various sensors onboard the sense hat, we refer to [waveshare's sense hat docs](https://www.waveshare.com/wiki/Sense_HAT_(B)) or most notably, the Feature and I2C device addresses sections quoted below:

### Sensor descriptions

- Onboard ICM20948 (3-axis accelerometer, 3-axis gyroscope, and 3-axis magnetometer), detects movement, orientation, and magnetic.
- Onboard SHTC3 digital temperature and humidity sensor, allows monitoring of the environment.
- Onboard LPS22HB barometric pressure sensor, allows monitoring of the environment.
- Onboard TCS34725 color sensor, identifies the color of a nearby object.
- Onboard ADS1015 ADC, 4-ch 12-bit precision, AD expansion to support more external sensors.

### Sensor I2C device addresses
- ADS1015: 0x48
- ICM-20948: 0x68
- LPS22HB: 0x5C
- SHTC3: 0x70
- TCS34725: 0x29

```python
# example showing detected i2c addresses
result, code = my_container.execute("i2cdetect -y 1")
print(result)
```

If the above cell executes succesfully, we can see that the corresponding i2c device addresses of the sense hat's onboard sensors all show up as expected.

## Reading values from various sensors on the sense hat using AdaFruit blinka library and each sensor's respective breakout cicuitpython pip module

For each sensor, we use its respective adafruit-cicuitpython library. For convenience, the image we provisioned for this tutorial already has all the dependencies installed.

Here are the respective Adafruit CircuitPython tutorial pages for each sensor model:
- [ICM20948 (3-axis accelerometer, 3-axis gyroscope, and 3-axis magnetometer), detects movement, orientation, and magnetic CicuitPython module](https://learn.adafruit.com/adafruit-tdk-invensense-icm-20948-9-dof-imu/python-circuitpython#python-installation-of-icm20x-library-3069499)
- [SHTC3 digital temperature and humidity sensor, allows monitoring of the environment CicuitPython module](https://learn.adafruit.com/adafruit-sensirion-shtc3-temperature-humidity-sensor/python-circuitpython#python-installation-of-shtc3-library-3065209)
- [LPS22HB barometric pressure sensor, allows monitoring of the environment CicuitPython module](https://learn.adafruit.com/adafruit-lps25-pressure-sensor/python-circuitpython#python-installation-of-lps2x-library-3056734)
- [TCS34725 color sensor, identifies the color of a nearby object CircuitPython module](https://learn.adafruit.com/adafruit-color-sensors/python-circuitpython#python-installation-of-tcs34725-library-2998106)
- [ADS1015 ADC, 4-ch 12-bit precision, AD expansion to support more external sensors CircuitPython module](https://learn.adafruit.com/adafruit-4-channel-adc-breakouts/python-circuitpython#python-installation-of-ads1x15-library-2997261)

You will notice that some of these CicuitPython modules support miltiple different sensors, such as the ```ads1x15``` module that supports both the ```ads1015``` sensor that is onboard the sense hat and another model, the ```ads1115```. For these specific sensors, we made sure to specify the the i2c address when initializing the CircuitPython module to avoid errors related to default values pointing to another model of the same series.

### Example code snippet used to test the ADS1015 Analog to digital converter (full code can be found under /examples directory)
```
# We specify the exact i2c address for the ADC (0x48), which can be verified against the I2C map we previously displayed with i2cdetect
ads = ADS.ADS1015(i2c, address=0x48)
```

**Important note** All of the example code scripts used below to read values from the sensors are available under the ```/examples``` directory

## Using SHTC3, the temperatuure and humidity sensor

```python
script_file = "examples/SHTC3_temp_and_humidity_sensor_test.py"
result, code = my_container.execute(f"python3 {script_file}")
print(result)
```

## Using ADS1015, the Analog to digital converter

```python
script_file = "examples/ADS1015_analog_to_digital_test.py"
result, code = my_container.execute(f"python3 {script_file}")
print(result)
```

## Using ICM20948, the 3-axis accelerometer, 3-axis gyroscope, and 3-axis magnetometer

```python
script_file = "examples/ICM-20948_9-axis_sensor_test.py"
result, code = my_container.execute(f"python3 {script_file}")
print(result)
```

## Using LPS22HB, the barometric pressure sensor

The temperature value here is used for compensation and should not be used as a temperature reading

```python
script_file = "examples/LPS22HB_air_pressure_sensor_test.py"
result, code = my_container.execute(f"python3 {script_file}")
print(result)
```

## Using TCS34725, the color sensor

```python
script_file = "examples/TCS34725_color_recognition_sensor_test.py"
result, code = my_container.execute(f"python3 {script_file}")
print(result)
```

## Cleaning up

```python
# delete the container so it doesn't hang around
my_container.delete()
```

```python
# deleting the lease will free up the device now, instead of waiting for it to expire later
container_lease.delete()
```

## Appendix — Part B example scripts (from the source artifact `examples/` directory)

Part B runs these scripts *inside the container* (they ship in the image under `/examples` and are also provided in the artifact's `examples/` folder). Reproduced verbatim for grounding.

### `examples/SHTC3_temp_and_humidity_sensor_test.py`
```python
import board
import busio
import adafruit_shtc3

i2c = busio.I2C(board.SCL, board.SDA)
sensor = adafruit_shtc3.SHTC3(i2c)

print("SHTC3 Temperature: %0.1f C" % sensor.temperature)
print("SHTC3 Humidity: %0.1f %%" % sensor.relative_humidity)
```

### `examples/ADS1015_analog_to_digital_test.py`
```python
import board
from adafruit_ads1x15 import ADS1015, AnalogIn, ads1x15

# Create the I2C bus
i2c = board.I2C()

# Create the ADC object using the I2C bus
ads = ADS1015(i2c)

# Create single-ended input on channel 0
chan = AnalogIn(ads, ads1x15.Pin.A0)

print("ADS1015 Analog Input:")
print("{:>5}\t{:>5}".format("raw", "v"))
print("{:>5}\t{:>5.3f}".format(chan.value, chan.voltage))
```

### `examples/ICM-20948_9-axis_sensor_test.py`
```python
import board
import busio
import adafruit_icm20x

i2c = busio.I2C(board.SCL, board.SDA)
icm = adafruit_icm20x.ICM20948(i2c, address=0x68)

print("ICM-20948 Acceleration: ", icm.acceleration)
print("ICM-20948 Gyro: ", icm.gyro)
print("ICM-20948 Magnetometer: ", icm.magnetic)
```

### `examples/LPS22HB_air_pressure_sensor_test.py`
```python
import board
import busio
import adafruit_lps2x

i2c = busio.I2C(board.SCL, board.SDA)
lps = adafruit_lps2x.LPS22(i2c, address=0x5C)

print("LPS22HB Pressure: %0.1f hPa" % lps.pressure)
print("LPS22HB Temperature: %0.1f C" % lps.temperature)
```

### `examples/TCS34725_color_recognition_sensor_test.py`
```python
import board
import busio
import adafruit_tcs34725

i2c = busio.I2C(board.SCL, board.SDA)
sensor = adafruit_tcs34725.TCS34725(i2c, address=0x29)

print("TCS34725 Color: ", sensor.color_rgb_bytes)
```
