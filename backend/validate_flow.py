import requests
import time
import logging

BACKEND_BASE = "https://remote-login.onrender.com"
TEST_DOMAIN = "reddit.com"

# How long to wait between checks for VNC readiness
WAIT_TIME_SECS = 10
# Max retries for polling
MAX_RETRIES = 30

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    try:
        logging.info("STEP 1: Create new session")
        response = requests.post(f"{BACKEND_BASE}/session")
        response.raise_for_status()
        session_info = response.json()
        session_id = session_info["session_id"]
        public_ip = session_info["ip"]
        vnc_url = session_info["url"]

        logging.info(f"Session created: ID={session_id}")
        logging.info(f"Public IP: {public_ip}")
        logging.info(f"VNC URL: {vnc_url}")

        # Check if VNC URL is reachable
        logging.info("STEP 2: Wait for VNC to become reachable")
        vnc_ready = False
        for attempt in range(MAX_RETRIES):
            try:
                r = requests.get(vnc_url, timeout=5)
                if r.status_code == 200:
                    vnc_ready = True
                    logging.info(f"VNC is ready (attempt {attempt+1})")
                    break
            except Exception:
                pass
            logging.info(f"VNC not ready yet... retrying in {WAIT_TIME_SECS}s")
            time.sleep(WAIT_TIME_SECS)

        if not vnc_ready:
            raise Exception("VNC did not become ready in time")

        logging.info("STEP 5: Terminate session & VM")

        delete_url = f"{BACKEND_BASE}/session/{session_id}"
        response = requests.delete(delete_url)
        response.raise_for_status()
        logging.info("Session terminated successfully")

        logging.info("VALIDATION SUCCESS: All steps passed!")

    except Exception as e:
        logging.error(f"VALIDATION FAILED: {e}")

if __name__ == "__main__":
    main()