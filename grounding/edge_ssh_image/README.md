# edge_ssh_image — SSH on CHI@Edge

**Source artifact:** `edge_ssh_image` · **Built from:** `SSH_on_chiedge_tutorial.ipynb` (single notebook)
**python-chi style:** functional (`chi.use_site`, `lease.create_lease`, `container.create_container`)

## What it does
Spins up an SSH-enabled **Ubuntu 22.04** container on CHI@Edge (which runs containers under Kubernetes), injects the user's RSA public key into the container's `authorized_keys`, attaches a floating IP, and prints the `ssh root@<ip>` command to connect. The container image applies sshd workarounds (root login, `AuthorizedKeysFile`, `pam_loginuid.so` optional) and runs `sshd -D`.

End-to-end flow: site/project setup → 1-day device lease (`raspberrypi4-64`) → launch SSH container (port 22) → upload key + `chmod 600` + append to `authorized_keys` → associate floating IP → destroy container.

## Exact reference values
| Item | Value |
|---|---|
| Site | `chi.use_site("CHI@Edge")` |
| Project | `chi.set("project_name", "Chameleon")` |
| machine_name | `"raspberrypi4-64"` (functional `add_device_reservation(..., machine_name=...)`) |
| device_name(s) | *none* — reserved by `machine_name` with `count=2` |
| device_profiles | *none* (not used in this notebook) |
| Container image | `image="ghcr.io/chameleoncloud/edge_ssh_image:latest"` |
| Exposed ports | `exposed_ports=[22]` |
| Other container args | `workdir="/home"`, `platform_version=2` |
| Lease duration | `lease.lease_duration(days=1)` |
| Key upload target | `chi.container.upload(uuid, "./edge_user_public_key", "/root/.ssh/")` |

## Key python-chi calls (in order)
```python
chi.use_site("CHI@Edge")
chi.set("project_name", "Chameleon")
start, end = lease.lease_duration(days=1)
lease.add_device_reservation(reservations, count=2, machine_name=machine_name)
container_lease = lease.create_lease(lease_name, reservations)
lease.wait_for_active(lease_id)
container.create_container(container_name, image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
                           workdir="/home", exposed_ports=[22],
                           reservation_id=lease.get_device_reservation(lease_id), platform_version=2)
chi.container.upload(my_container.uuid, "./edge_user_public_key", "/root/.ssh/")
chi.container.execute(my_container.uuid, '/bin/bash -c "chmod 600 /root/.ssh/authorized_keys"')
chi.container.execute(my_container.uuid, '/bin/bash -c "cat /root/.ssh/edge_user_public_key >> /root/.ssh/authorized_keys"')
chi.container.associate_floating_ip(my_container.uuid)
chi.container.destroy_container(my_container.uuid)
```

## Container image (Dockerfile summary)
`FROM ubuntu:22.04` → install `openssh-server` → `PermitRootLogin yes` → enable `AuthorizedKeysFile .ssh/authorized_keys .ssh/authorized_keys2` → `pam_loginuid.so` from `required` to `optional` → `mkdir /root/.ssh` + `touch /root/.ssh/authorized_keys` → `EXPOSE 22` → `CMD ["/usr/sbin/sshd", "-D"]`.

## Notes (preserved source quirks — not corrected)
> NOTE: The artifact's `edge_user_public_key` file contains only the placeholder line `replace this line with your RSA public key`; replace it with your real one-line RSA public key before running the upload cell.

> NOTE: `count=2` reserves two `raspberrypi4-64` devices, but only one reservation is used for the container (`lease.get_device_reservation(lease_id)`).

> NOTE: This notebook uses the **functional** python-chi API. The object-oriented API (`lease.Lease()` / `container.Container()`) is used by the other two artifacts but not here.

## Crux
device `raspberrypi4-64` (machine_name, `count=2`) + device_profiles: **none** + image `ghcr.io/chameleoncloud/edge_ssh_image:latest` (port 22)
