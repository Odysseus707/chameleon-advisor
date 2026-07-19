# SSH on CHI@Edge containers

> **Grounding note.** Built from the single source notebook `SSH_on_chiedge_tutorial.ipynb`. Code and exact strings are preserved verbatim; stale execution outputs were omitted.
>
> This notebook uses the **functional** python-chi style (`lease.create_lease()`, `container.create_container()`). The object-oriented style (`lease.Lease()`, `container.Container()`) used by the other artifacts is *not* used here.
>
> **Crux:** machine_name `raspberrypi4-64` (`count=2`) · device_profiles: *none* · image `ghcr.io/chameleoncloud/edge_ssh_image:latest` · exposed port `22`.

> NOTE: The `edge_user_public_key` file in the source artifact contains only the placeholder line `replace this line with your RSA public key`. You must replace it with your real one-line RSA public key before running the upload cell below.

```python
import chi
# Before we go any further, we need to select which Chameleon site we will be using.
chi.use_site("CHI@Edge")
```

```python
chi.set("project_name", "Chameleon")
```

```python
from chi import container
from chi import lease
```

## Creating a 1-day lease

We are creating a short 1 day lease for a raspberry pi 4 device

> NOTE: `count=2` reserves two `raspberrypi4-64` devices, but only one reservation is later used for the container (via `lease.get_device_reservation(lease_id)`). Preserved verbatim from the source.

```python
# machine name refers to the "type" of device
machine_name = "raspberrypi4-64"

# get dates for lease start and end
start, end = lease.lease_duration(days=1)

# make a unique name for the lease
lease_name = f"ssh-{machine_name}-{start}"

reservations = []
lease.add_device_reservation(reservations, count=2, machine_name=machine_name)
container_lease = lease.create_lease(lease_name, reservations)
lease_id = container_lease["id"]

print(f"created lease with name {lease_name} and uuid {lease_id}, waiting for it to start. This can take up to 60s.")
lease.wait_for_active(lease_id)
print("Done!")
```

## Starting the container

The image we are using is a base [ubuntu 22.04 image](https://github.com/ChameleonCloud/edge_ssh_image) where we install a variety of utilities and apply some modifications to the sshd config before starting the sshd daemon.

```python
print("Requesting container ... This may take a while as the large container image is being downloaded")

# Set a name for the container. Because CHI@Edge uses Kubernetes, ensure that underscores aren't in the name
container_name = f"tutorial-{machine_name}-ssh".replace("_","-")

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
    print(f"please stop and/or delete {container_name} and try again")
else:
    print(f"Successfully created container: {container_name}!")
```

## Adding your public key to the authorized keys within the container

**Important** Please first place your RSA public key in one line in the 'edge_user_public_key' text file. The following cells will then upload the file to the running container, and copy over the key to the authorized keys file after setting the appropriate permissions.

```python
chi.container.upload(my_container.uuid, "./edge_user_public_key", "/root/.ssh/")
```

```python
cmd = "/bin/bash -c \"chmod 600 /root/.ssh/authorized_keys\""
chi.container.execute(my_container.uuid, cmd)
```

```python
cmd = "/bin/bash -c \"cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys\""
chi.container.execute(my_container.uuid, cmd)
```

## SSH'ing into the container

if ssh'ing into the device hangs forever when connecting to device part, please release the floating IP via the chi@edge openstack dashboard and rerun the cell below

```python
ip_address = chi.container.associate_floating_ip(my_container.uuid)

print("use the following command to ssh into the container: ssh root@" + ip_address)
```

## Destroying the container

Destroying the container after use is good practice to keep your device running smoothly, use when needed.

```python
chi.container.destroy_container(my_container.uuid)
```
