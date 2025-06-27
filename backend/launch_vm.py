import oci
import json
from base64 import b64encode

with open("config.json") as f:
    cfg = json.load(f)

oci_config = oci.config.from_file("/etc/secrets/config")

compute = oci.core.ComputeClient(oci_config)
network = oci.core.VirtualNetworkClient(oci_config)

def launch_instance(session_id:str, domain:str):
    
    with open(cfg["ssh_key_path"]) as f:
        ssh_key = f.read()

    duckdns_token = cfg["duckdns_token"]

    startup_script = f"""#!/bin/bash
    sudo iptables -F
    sudo iptables -X
    sudo iptables -t nat -F
    sudo iptables -t nat -X
    sudo iptables -t mangle -F
    sudo iptables -t mangle -X
    sudo iptables -P INPUT ACCEPT
    sudo iptables -P FORWARD ACCEPT
    sudo iptables -P OUTPUT ACCEPT

    # Install Caddy
    sudo apt update
    sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg lsb-release
    curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt update
    sudo apt install -y caddy

    echo "Updating DuckDNS..."
    curl "https://www.duckdns.org/update?domains=remote-login&token={duckdns_token}&ip="

    # Start virtual display :0 using Xvfb
    Xvfb :1 -screen 0 1280x720x24 &

    # Wait for Xvfb to start
    sleep 2

    # Start LXDE session with DISPLAY=:1
    env DISPLAY=:1 startlxde &

    # Wait for lxde to start
    sleep 5

    # Ensure Desktop directory exists
    mkdir -p /home/ubuntu/Desktop

    cp /usr/share/applications/google-chrome.desktop /home/ubuntu/Desktop/
    chmod +x /home/ubuntu/Desktop/google-chrome.desktop
    chown ubuntu:ubuntu /home/ubuntu/Desktop/google-chrome.desktop
    sudo chown -R ubuntu:ubuntu /home/ubuntu/chrome-profile

    # Clear Chrome profile to start fresh
    rm -rf /home/ubuntu/chrome-profile/*

    # Automatically starting google chrome
    env DISPLAY=:1 google-chrome \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --disable-software-rasterizer \
    --disable-background-timer-throttling \
    --disable-renderer-backgrounding \
    --disable-backgrounding-occluded-windows \
    --disable-features=TranslateUI,VizDisplayCompositor \
    --disable-ipc-flooding-protection \
    --disable-web-security \
    --disable-features=VizDisplayCompositor \
    --disable-threaded-animation \
    --disable-threaded-scrolling \
    --disable-checker-imaging \
    --disable-new-bookmark-apps \
    --disable-background-downloads \
    --disable-background-networking \
    --disable-client-side-phishing-detection \
    --disable-default-apps \
    --disable-extensions \
    --disable-hang-monitor \
    --disable-plugins \
    --disable-popup-blocking \
    --disable-prompt-on-repost \
    --disable-sync \
    --disable-translate \
    --disable-web-resources \
    --memory-pressure-off \
    --no-first-run \
    --no-default-browser-check \
    --password-store=basic \
    --remote-debugging-port=9222 \
    --window-size=1280,720 \
    --user-data-dir=/home/ubuntu/chrome-profile &

    sudo chown -R ubuntu:ubuntu /home/ubuntu/chrome-profile

    # Start x11vnc server with DISPLAY=:1
    env DISPLAY=:1 x11vnc -display :1 -forever -nopw &

    sleep 5
    cd /home/ubuntu/noVNC-master
    ./utils/novnc_proxy --vnc 127.0.0.1:5900 --listen 0.0.0.0:6080 &

    # Write caddyfile
    sudo bash -c "echo '{domain} {{
        reverse_proxy localhost:6080
    }}' > /etc/caddy/Caddyfile"

    # Restart Caddy
    sudo systemctl restart caddy

    cd /home/ubuntu
    export PATH=$PATH:/home/ubuntu/.local/bin
    export PYTHONPATH=$PYTHONPATH:/home/ubuntu/.local/lib/python3.10/site-packages
    nohup uvicorn fetch_cookies:app --host 0.0.0.0 --port 8080 > /home/ubuntu/cookie.log 2>&1 &
    """

    user_data_encoded = b64encode(startup_script.encode()).decode()

    launch_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=cfg["compartment_id"],
        display_name=f"session-{session_id[:8]}",
        availability_domain=cfg["availability_domain"],
        shape=cfg["shape"],
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=4,
            memory_in_gbs=32
        ),
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