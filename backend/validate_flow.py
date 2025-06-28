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

def open_url_in_chrome(ip, url_to_open):
    try:
        endpoint = f"http://{ip}:9222/json/new?{url_to_open}"
        resp = requests.get(endpoint, timeout=5)
        if resp.ok:
            logging.info(f"Opened tab: {url_to_open}")
        else:
            logging.info(f"Failed to open tab: {resp.status_code} {resp.text}")
    except Exception as e:
        logging.info(f"Exception while opening tab: {e}")

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

        logging.info("STEP 3: Simulate cookie extraction")

        open_url_in_chrome(public_ip, f"https://{TEST_DOMAIN}")

        extract_url = f"{BACKEND_BASE}/extract_cookies"
        extract_params = {
            "ip": public_ip,
            "domain": TEST_DOMAIN
        }

        response = requests.get(extract_url, params=extract_params, timeout=30)
        response.raise_for_status()
        extract_result = response.json()
        access_token = extract_result["access_token"]
        cookie = extract_result["cookies"]

        logging.info(f"Extracted cookie: {cookie}")

        logging.info(f"Access Token: {access_token}")

        logging.info("STEP 4: Retrieve stored cookies using access token")

        cookies_url = f"{BACKEND_BASE}/cookies"
        params = {
            "session_id": session_id,
            "access_token": access_token
        }

        response = requests.get(cookies_url, params=params, timeout=30)
        response.raise_for_status()
        cookies_data = response.json()

        logging.info(f"Retrieved cookies: {cookies_data}")

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