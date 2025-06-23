import oci
import json
from base64 import b64encode

with open("config.json") as f:
    cfg = json.load(f)

oci_config = oci.config.from_file()

compute = oci.core.ComputeClient(oci_config)
network = oci.core.VirtualNetworkClient(oci_config)

def launch_instance(session_id:str):
    
    with open(cfg["ssh_key_path"]) as f:
        ssh_key = f.read()

    startup_script = """#!/bin/bash
    sudo iptables -F
    sudo iptables -X
    sudo iptables -t nat -F
    sudo iptables -t nat -X
    sudo iptables -t mangle -F
    sudo iptables -t mangle -X
    sudo iptables -P INPUT ACCEPT
    sudo iptables -P FORWARD ACCEPT
    sudo iptables -P OUTPUT ACCEPT

    # Start virtual display :0 using Xvfb
    Xvfb :1 -screen 0 1280x720x24 &

    # Wait for Xvfb to start
    sleep 2

    # Start LXDE session with DISPLAY=:1
    env DISPLAY=:1 startlxde &

    # Automatically starting google chrome
    env DISPLAY=:1 google-chrome --no-sandbox --disable-gpu --disable-software-rasterizer &


    # Start x11vnc server with DISPLAY=:1
    env DISPLAY=:1 x11vnc -display :1 -forever -nopw &

    cd /home/ubuntu/noVNC-master
    ./utils/novnc_proxy --vnc 127.0.0.1:5900 --listen 0.0.0.0:6080 &
    """

    user_data_encoded = b64encode(startup_script.encode()).decode()

    launch_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=cfg["compartment_id"],
        display_name=f"session-{session_id[:8]}",
        availability_domain=cfg["availability_domain"],
        shape=cfg["shape"],
        metadata={
            "ssh_authorized_keys":ssh_key,
            "user_data": user_data_encoded
        },
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            source_type="image",
            image_id=cfg["image_id"],
            boot_volume_size_in_gbs=50
        ),
        subnet_id=cfg["subnet_id"],
        is_pv_encryption_in_transit_enabled=True,
        freeform_tags={"session_id": session_id}
    )

    instance = compute.launch_instance(launch_details)

    instance = oci.wait_until(
        compute,
        compute.get_instance(instance.data.id),
        'lifecycle_state',
        'RUNNING',
        max_wait_seconds=300
    ).data

    vnic_attachments = compute.list_vnic_attachments(
        compartment_id=cfg["compartment_id"], 
        instance_id=instance.id
    ).data

    vnic_id = vnic_attachments[0].vnic_id
    vnic = network.get_vnic(vnic_id).data
    
    return vnic.public_ip

def terminate_instance(session_id:str):
    instances = compute.list_instances(
        compartment_id=cfg["compartment_id"],
        display_name=None
    ).data

    for instance in instances:
        if instance.lifecycle_state.upper() != "TERMINATED":
            inst = compute.get_instance(instance_id=instance.id).data
            tags = inst.freeform_tags
            if tags.get("session_id") == session_id:
                compute.terminate_instance(instance_id=instance.id)
                return
    
    raise Exception(f"No running instances found for session id: {session_id}")