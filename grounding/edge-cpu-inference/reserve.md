---
author: 'Deepak Chaurasiya'
jupyter:
  kernelspec:
    display_name: Python 3
    name: python3
  nbformat: 4
  nbformat_minor: 0
---


:::{.cell}
# Run a single user notebook server on Chameleon

This notebook describes how to reserve resources for an edge device. This allows you to run experiments requiring inferences on edge devices like Raspberry Pi, Coral and, Nvidia and compute resources on Chameleon using a Jupyter notebook interface.
:::

:::{.cell}
## Provision the resource

### Check resource availability

This notebook will try to reserve a Raspberry Pi on CHI@Edge - pending availability. Before you begin, you should check the host calendar at https://chi.edge.chameleoncloud.org/project/leases/calendar/device/ to see what node types are available.

### Chameleon configuration

You can change your Chameleon project name (if not using the one that is automatically configured in the JupyterHub environment) and the site on which to reserve resources (depending on availability) in the following cell.
:::

:::{.cell .code}
```
import chi, os, time
from chi import lease
from chi import server
from chi import container

PROJECT_NAME = os.getenv('OS_PROJECT_NAME') # change this if you need to
chi.use_site("CHI@Edge")
chi.set("project_name", PROJECT_NAME)
username = os.getenv('USER') # all exp resources will have this prefix
```
:::

:::{.cell}
If you need to change the details of the Chameleon server, e.g. use a different edge device (NODE_TYPE), or a different node type depending on availability, you can do that in the following cell.
:::

:::{.cell .code}
```
NODE_TYPE = 'raspberrypi4-64'
expname = "edge-cpu"
```
:::

:::{.cell .code}
```
res = []
lease.add_device_reservation(res, machine_name=NODE_TYPE, count=1)

start_date, end_date = lease.lease_duration(days=0, hours=10)
# if you won't start right now - comment the line above, uncomment two lines below
# start_date = '2024-04-02 15:24' # manually define to desired start time 
# end_date = '2024-04-03 01:00' # manually define to desired start time 

l = lease.create_lease(f"{username}-{NODE_TYPE}", res, start_date=start_date, end_date=end_date)
l = lease.wait_for_active(l["id"])  #Comment this line if the lease starts in the future
```
:::

:::{.cell .code}
```
# continue here, whether using a lease created just now or one created earlier
l = lease.get_lease(f"{username}-{NODE_TYPE}")
l['id']
```
:::


:::{.cell}
### Delete the container

Finally, we should stop and delete our lease so that other users can use the resources and create their own leases. To delete our lease, we can run the following cells:

This section is designed to work as a “standalone” portion - you can
come back to this notebook, ignore the top part, and just run this
section to delete your resources
:::

:::{.code .cell}
```
# setup environment - if you made any changes in the top part, make the same changes here
import chi, os
from chi import lease

PROJECT_NAME = os.getenv('OS_PROJECT_NAME') # change this if you need to
chi.use_site("CHI@Edge")
chi.set("project_name", PROJECT_NAME)
username = os.getenv('USER') 

lease = chi.lease.get_lease(f"{username}-{NODE_TYPE}")
```
:::

:::{.code .cell}
```
DELETE = False #Default value is False to prevent any accidental deletes. Change it to True for deleting the resources

if DELETE:

    # delete lease
    chi.lease.delete_lease(lease["id"])
```
:::
