"""
                                     OCI Instance Manager
===================================================================================================

An Oracle Cloud Infrastructure (OCI) instance management system for launching and terminating
compute instances with automated browser environments. This module provides functionality for
creating on-demand cloud instances with pre-configured VNC access, web proxy setup, and
automatic termination capabilities for session-based workloads.

Features:
- Dynamic OCI compute instance provisioning
- Automated browser environment setup (Chrome + VNC)
- Web-based remote desktop access via noVNC
- Reverse proxy configuration using Caddy
- Automatic instance termination after timeout
- Session-based instance tracking and management
- FastAPI cookie extraction service deployment

Use Cases:
- Isolated web scraping sessions
- Remote desktop access for development
- Cookie extraction and session management
- Automated browser automation workflows

Dependencies:
- oci: Oracle Cloud Infrastructure SDK
  - oci.config: Configuration management
  - oci.core.ComputeClient: Compute instance operations
  - oci.core.VirtualNetworkClient: Network interface management
  - oci.core.models: Data models for API requests

- json: Configuration file parsing and data serialization
- base64: Base64 encoding for user data scripts

Configuration Requirements:
- config.json: Application configuration file containing:
  - compartment_id: OCI compartment identifier
  - availability_domain: Target availability domain
  - shape: Instance shape specification
  - image_id: Base image for instance creation
  - subnet_id: Network subnet identifier
  - ssh_key_path: Path to SSH public key file
- /etc/secrets/config: Path to OCI authentication configuration file in vercel

Security Considerations:
- SSH key-based authentication
- Automatic firewall rule clearing for development
- Chrome security features disabled for automation
- Automatic instance termination prevents resource waste
"""


# =============================================================================
# IMPORTS
# =============================================================================

import oci
import json
from base64 import b64encode


# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

# Load application configuration from JSON file
# Contains instance specifications, network settings, and resource identifiers
with open("config.json") as f:
    cfg = json.load(f)

# Initialize OCI configuration from standard config file
# Handles authentication credentials, region settings, and API endpoints
oci_config = oci.config.from_file("/etc/secrets/config")

# Initialize OCI service clients for compute and networking operations
compute = oci.core.ComputeClient(oci_config)                # Manage compute instances lifecycle
network = oci.core.VirtualNetworkClient(oci_config)         # Handle network interface operations


# =============================================================================
# INSTANCE MANAGEMENT FUNCTIONS
# =============================================================================

def launch_instance(session_id:str, domain:str):
    """
    Launch a new OCI compute instance with automated browser environment setup.
    
    This function creates a fully configured cloud instance with the following components:
    1. Ubuntu-based compute instance with specified hardware configuration
    2. Automated browser environment (Chrome + LXDE desktop)
    3. VNC server for remote desktop access
    4. noVNC web interface for browser-based connectivity
    5. Caddy reverse proxy for secure domain access
    6. FastAPI service for cookie extraction
    7. Automatic termination after 15 minutes
    
    The instance is provisioned with a comprehensive startup script that handles:
    - System updates and package installation
    - Desktop environment configuration
    - Browser setup with automation-friendly settings
    - Network service initialization
    - Security configuration for development use
    
    Args:
        session_id (str): Unique identifier for tracking the instance session.
                         Used for resource tagging and cleanup operations.
        domain (str): Target domain name for reverse proxy configuration.
                     Caddy will route traffic from this domain to the VNC interface.
        
    Returns:
        str: Public IP address of the launched instance.
        
    Raises:
        oci.exceptions.ServiceError: If instance creation fails due to quota limits,
                                   invalid configuration, or OCI service issues.
        FileNotFoundError: If SSH key file specified in config is not found.
        json.JSONDecodeError: If configuration file contains invalid JSON.
        
    Instance Configuration:
        - Shape: Configurable via config.json (default: flexible shapes supported)
        - Resources: 4 OCPUs, 32GB RAM, 50GB boot volume
        - OS: Ubuntu-based image with pre-installed development tools
        - Network: Public subnet with internet gateway access
        - Security: SSH key authentication, development firewall rules
        
    Startup Process:
        1. Firewall configuration for development environment
        2. Caddy web server installation and configuration
        3. X11 virtual display setup (Xvfb on :1)
        4. LXDE desktop environment initialization
        5. Chrome browser launch with automation flags
        6. VNC server startup for remote access
        7. noVNC web interface deployment
        8. FastAPI cookie service deployment
        9. Automatic termination timer (15 minutes)
    """
    
    # Load SSH public key for instance authentication
    # Key must be in OpenSSH format for OCI compatibility
    with open(cfg["ssh_key_path"]) as f:
        ssh_key = f.read()

    # Comprehensive startup script for instance initialization
    # Configures complete browser automation environment
    startup_script = f"""#!/bin/bash
    # =================================================================
    # FIREWALL CONFIGURATION
    # =================================================================
    # Clear all existing firewall rules
    sudo iptables -F                    # Flush all rules
    sudo iptables -X                    # Delete all custom chains
    sudo iptables -t nat -F             # Clear NAT table
    sudo iptables -t nat -X             # Delete NAT chains
    sudo iptables -t mangle -F          # Clear mangle table
    sudo iptables -t mangle -X          # Delete mangle chains
    sudo iptables -P INPUT ACCEPT       # Accept all incoming traffic
    sudo iptables -P FORWARD ACCEPT     # Accept all forwarded traffic
    sudo iptables -P OUTPUT ACCEPT      # Accept all outgoing traffic

    # =================================================================
    # CADDY WEB SERVER INSTALLATION
    # =================================================================
    # Install Caddy for reverse proxy and HTTPS termination
    sudo apt update
    sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg lsb-release

    # Add Caddy repository GPG key for package verification
    curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    
    # Add Caddy repository to package sources
    echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    
    # Install Caddy web server
    sudo apt update
    sudo apt install -y caddy

    # =================================================================
    # VIRTUAL DISPLAY SETUP
    # =================================================================
    # Start virtual X11 display for headless browser operation
    # Display :1 with 1280x720 resolution and 24-bit color depth
    # Start virtual display :0 using Xvfb
    Xvfb :1 -screen 0 1280x720x24 &

    # Wait for Xvfb to start
    sleep 2

    # =================================================================
    # DESKTOP ENVIRONMENT INITIALIZATION
    # =================================================================
    # Start LXDE lightweight desktop environment on virtual display
    env DISPLAY=:1 startlxde &

    # Wait for lxde to start
    sleep 2

    # =================================================================
    # DESKTOP SHORTCUTS CONFIGURATION
    # =================================================================
    # Ensure Desktop directory exists for user shortcuts
    mkdir -p /home/ubuntu/Desktop

    # Create Chrome desktop shortcut for easy access
    cp /usr/share/applications/google-chrome.desktop /home/ubuntu/Desktop/
    chmod +x /home/ubuntu/Desktop/google-chrome.desktop
    chown ubuntu:ubuntu /home/ubuntu/Desktop/google-chrome.desktop
    sudo chown -R ubuntu:ubuntu /home/ubuntu/chrome-profile

    # =================================================================
    # CHROME PROFILE MANAGEMENT
    # =================================================================
    # Clear existing Chrome profile for fresh session
    # Ensures clean state for each instance launch
    rm -rf /home/ubuntu/chrome-profile/*

    # =================================================================
    # CHROME BROWSER LAUNCH
    # =================================================================
    # Start Chrome with extensive automation-friendly configuration
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

    # Ensure proper ownership of Chrome profile directory
    sudo chown -R ubuntu:ubuntu /home/ubuntu/chrome-profile

    # =================================================================
    # VNC SERVER CONFIGURATION
    # =================================================================
    # Start x11vnc server for remote desktop access
    # Connects to virtual display :1 with persistent connection
    env DISPLAY=:1 x11vnc -display :1 -forever -nopw &

    # Wait for VNC server initialization
    sleep 2

    # =================================================================
    # NOVNC WEB INTERFACE SETUP
    # =================================================================
    # Start noVNC proxy for browser-based VNC access
    # Bridges VNC protocol to WebSocket for web browsers
    cd /home/ubuntu/noVNC-master
    ./utils/novnc_proxy --vnc 127.0.0.1:5900 --listen 0.0.0.0:6080 &

    # =================================================================
    # REVERSE PROXY CONFIGURATION
    # =================================================================
    # Configure Caddy reverse proxy for domain-based access
    # Routes external domain traffic to internal noVNC service
    sudo bash -c "echo '{domain} {{
        reverse_proxy localhost:6080
    }}' > /etc/caddy/Caddyfile"

    # Restart Caddy to apply new configuration
    sudo systemctl restart caddy

    # =================================================================
    # FASTAPI COOKIE SERVICE DEPLOYMENT
    # =================================================================
    # Start FastAPI service for cookie extraction functionality
    cd /home/ubuntu
    export PATH=$PATH:/home/ubuntu/.local/bin
    export PYTHONPATH=$PYTHONPATH:/home/ubuntu/.local/lib/python3.10/site-packages

    # Start cookie extraction service in background with logging
    nohup uvicorn fetch_cookies:app --host 0.0.0.0 --port 8080 > /home/ubuntu/cookie.log 2>&1 &

    # =================================================================
    # AUTOMATIC TERMINATION SETUP
    # =================================================================
    # Configure automatic instance shutdown after 15 minutes
    # Prevents runaway costs and ensures resource cleanup
    (sleep 900; sudo shutdown -h now) &
    """

    # Encode startup script for OCI user data
    # Base64 encoding required for cloud-init processing
    user_data_encoded = b64encode(startup_script.encode()).decode()

    # =================================================================
    # INSTANCE LAUNCH CONFIGURATION
    # =================================================================
    # Configure comprehensive instance launch parameters
    launch_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=cfg["compartment_id"],                   # Target OCI compartment
        display_name=f"session-{session_id[:8]}",               # Human-readable instance name
        availability_domain=cfg["availability_domain"],         # Target availability domain
        shape=cfg["shape"],                                     # Instance shape specification

        # Hardware resource allocation (Only for Flex shapes)
        # REMOVE if not using a Flex shape
        # shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
        #     ocpus=4,
        #     memory_in_gbs=32
        # ),

        # Instance metadata and initialization
        metadata={
            "ssh_authorized_keys":ssh_key,
            "user_data": user_data_encoded
        },

        # Boot volume and image configuration
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            source_type="image",                   # Launch from image
            image_id=cfg["image_id"],              # Base Ubuntu image ID
            boot_volume_size_in_gbs=50             # 50GB boot volume for applications
        ),

        # Network configuration
        subnet_id=cfg["subnet_id"],
        is_pv_encryption_in_transit_enabled=True,

        # Resource tagging for management
        freeform_tags={"session_id": session_id}
    )

    # =================================================================
    # INSTANCE LAUNCH AND MONITORING
    # =================================================================
    # Launch the instance with configured parameters
    instance = compute.launch_instance(launch_details)

    # Wait for instance to reach RUNNING state
    # Timeout after 5 minutes if instance fails to start
    instance = oci.wait_until(
        compute,
        compute.get_instance(instance.data.id),
        'lifecycle_state',
        'RUNNING',
        max_wait_seconds=300
    ).data

    # =================================================================
    # NETWORK INTERFACE DISCOVERY
    # =================================================================
    # Retrieve virtual network interface card (VNIC) attachments
    # Required to obtain public IP address for external access
    vnic_attachments = compute.list_vnic_attachments(
        compartment_id=cfg["compartment_id"], 
        instance_id=instance.id
    ).data

    # Get primary VNIC ID
    vnic_id = vnic_attachments[0].vnic_id
    # Retrieve VNIC details including public IP
    vnic = network.get_vnic(vnic_id).data
    
    # Return public IP for external connectivity
    return vnic.public_ip

def terminate_instance(session_id:str):
    """
    Terminate a running OCI compute instance associated with a specific session.
    
    This function searches for and terminates compute instances that match the
    provided session ID. It performs a comprehensive search across all running
    instances in the configured compartment and safely terminates only the
    instance tagged with the specified session identifier.
    
    The termination process includes:
    1. Comprehensive instance enumeration in the compartment
    2. Lifecycle state validation to avoid terminating already stopped instances
    3. Session ID tag verification for safe instance identification
    4. Graceful instance termination with proper cleanup
    
    Args:
        session_id (str): Unique session identifier used to locate the target instance.
                         Must match the session_id tag applied during instance creation.
        
    Returns:
        None: Function completes silently on successful termination.
        
    Raises:
        Exception: If no running instances are found with the specified session ID.
                  Indicates either the instance was already terminated, never existed,
                  or the session ID was incorrectly specified.
        
        oci.exceptions.ServiceError: If OCI API calls fail due to:
            - Authentication/authorization issues
            - Network connectivity problems
            - Service unavailability
            - Invalid instance state transitions
        
    Safety Features:
        - Only targets instances with matching session_id tag
        - Skips already terminated instances to prevent errors
        - Validates instance existence before termination attempts
        - Provides clear error messages for troubleshooting
        
    Termination Process:
        1. List all instances in the configured compartment
        2. Filter instances by lifecycle state (exclude terminated)
        3. Retrieve detailed instance information including tags
        4. Match session_id tag against provided identifier
        5. Execute termination command for matching instance
        6. Return immediately after successful termination
                
    Resource Management:
        - Prevents resource waste from forgotten instances
        - Ensures proper cleanup of temporary environments
        - Reduces cloud infrastructure costs
        - Maintains clean resource inventory
    """

    # =================================================================
    # INSTANCE ENUMERATION
    # =================================================================
    # Retrieve comprehensive list of all instances in compartment
    # Includes instances in all lifecycle states for complete visibility
    instances = compute.list_instances(
        compartment_id=cfg["compartment_id"],
        display_name=None
    ).data

    # =================================================================
    # INSTANCE SEARCH AND TERMINATION
    # =================================================================
    # Iterate through all discovered instances to find session match
    for instance in instances:
        # Skip instances that are already terminated
        # Prevents unnecessary API calls and potential errors
        if instance.lifecycle_state.upper() != "TERMINATED":

            # Retrieve detailed instance information including tags
            # Required to access freeform_tags for session identification
            inst = compute.get_instance(instance_id=instance.id).data
            tags = inst.freeform_tags

            # Check if instance has matching session_id tag
            if tags.get("session_id") == session_id:
                # Execute instance termination
                # Instance will transition through TERMINATING to TERMINATED state
                compute.terminate_instance(instance_id=instance.id)
                return
    
    # =================================================================
    # ERROR HANDLING
    # =================================================================
    # Raise exception if no matching instance found
    # Indicates session_id mismatch or instance already terminated
    raise Exception(f"No running instances found for session id: {session_id}")
