import oci
import json
import os

with open("config.json") as f:
    cfg = json.load(f)

oci_config = oci.config.from_file()

compute = oci.core.ComputeClient(oci_config)
network = oci.core.VirtualNetworkClient(oci_config)

with open(cfg["ssh_key_path"]) as f:
    ssh_key = f.read()

launch_details = oci.core.models.LaunchInstanceDetails(
    compartment_id=cfg["compartment_id"],
    display_name="session-instance",
    availability_domain=cfg["availability_domain"],
    shape=cfg["shape"],
    metadata={
        "ssh_authorized_keys":ssh_key
    },
    source_details=oci.core.models.InstanceSourceViaImageDetails(
        source_type="image",
        image_id=cfg["image_id"],
        boot_volume_size_in_gbs=50
    ),
    create_vnic_details=oci.core.models.CreateVnicDetails(
        assign_public_ip=True,
        subnet_id=cfg["subnet_id"],
        display_name="session-vnic",
        skip_source_dest_check=False
    )
)

print("Launcing Instance ...")
response = compute.launch_instance(launch_details)
instance=response.data
print(f"Instance ID: {instance.id}")

waiter = oci.wait_until(
    compute,
    compute.get_instance(instance.id),
    'lifecycle_state',
    'RUNNING',
    max_interval_seconds=300
)

vnic_attachments = compute.list_vnic_attachments(compartment_id=cfg["compartment_id"], instance_id=instance.id)
vnic_id = vnic_attachments.data[0].vnic_id
vnic = network.get_vnic(vnic_id).data
print(f"Public IP: {vnic.public_ip}")