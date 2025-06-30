"""
===================================================================================================
                           Remote Session Lifecycle Validator Script
===================================================================================================

This script verifies that the remote session API is fully functional by:
1. Creating a new ephemeral browser session using the FastAPI backend.
2. Polling the VNC URL until it becomes reachable, indicating that the VM, noVNC,
   and browser stack are operational.
3. Gracefully terminating the session and cleaning up resources.
4. Logging all steps for traceability.

This validation is critical for testing the entire flow end-to-end, including:
- FastAPI backend provisioning logic
- Oracle Cloud VM launch process
- Cloudflare DNS record propagation
- noVNC remote desktop service health
- Proper session teardown to prevent resource leaks

Use Case:
- CI/CD validation step after deployment.
- Manual debugging of orchestration logic.
- Health check for the remote session infrastructure.

Dependencies:
- requests: For HTTP requests to the backend and VNC.
- time: For retry loop delays.
- logging: For structured output to console.

===================================================================================================
"""

# =============================================================================
# IMPORTS & CONFIGURATION
# =============================================================================

import requests
import time
import logging


# =============================================================================
# CONFIGURATION VARIABLES
# =============================================================================

# Base URL of the FastAPI backend orchestrator
BACKEND_BASE = "https://remote-login.onrender.com"

# How long to wait between checks for VNC readiness
WAIT_TIME_SECS = 10

# Max retries for polling
MAX_RETRIES = 30

# Configure logging for structured output
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    """
    Runs the end-to-end session lifecycle validation:
    - Creates a new remote browser session.
    - Polls the VNC URL until the service becomes reachable.
    - Terminates the session using the DELETE endpoint.
    - Logs success or failure of the entire flow.
    """
    try:
        # =========================================================================
        # STEP 1: Create new remote session
        # =========================================================================
        logging.info("STEP 1: Create new session")
        response = requests.post(f"{BACKEND_BASE}/session")
        response.raise_for_status()

        # Extract session details from response
        session_info = response.json()
        session_id = session_info["session_id"]
        public_ip = session_info["ip"]
        vnc_url = session_info["url"]

        logging.info(f"Session created: ID={session_id}")
        logging.info(f"Public IP: {public_ip}")
        logging.info(f"VNC URL: {vnc_url}")

        # =========================================================================
        # STEP 2: Poll VNC URL for readiness
        # =========================================================================
        logging.info("STEP 2: Wait for VNC to become reachable")
        vnc_ready = False

        # Poll the VNC URL repeatedly until we get an HTTP 200 or hit max retries
        for attempt in range(MAX_RETRIES):
            try:
                r = requests.get(vnc_url, timeout=5)
                if r.status_code == 200:
                    vnc_ready = True
                    logging.info(f"VNC is ready (attempt {attempt+1})")
                    break
            except Exception:
                # Ignore exceptions during polling — usually connection refused
                pass

            logging.info(f"VNC not ready yet... retrying in {WAIT_TIME_SECS}s")
            time.sleep(WAIT_TIME_SECS)

        if not vnc_ready:
            raise Exception("VNC did not become ready in time")

        # =========================================================================
        # STEP 3: Terminate the session and clean up VM & DNS
        # =========================================================================
        logging.info("STEP 3: Terminate session & VM")

        delete_url = f"{BACKEND_BASE}/session/{session_id}"
        response = requests.delete(delete_url)
        response.raise_for_status()

        logging.info("Session terminated successfully")

        # =========================================================================
        # VALIDATION PASSED
        # =========================================================================
        logging.info("VALIDATION SUCCESS: All steps passed!")

    except Exception as e:
        # =========================================================================
        # VALIDATION FAILED
        # =========================================================================
        logging.error(f"VALIDATION FAILED: {e}")

if __name__ == "__main__":
    main()