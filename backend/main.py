from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import launch_vm
from uuid import uuid4
import time, socket, requests, json
from pymongo import MongoClient
from urllib.parse import quote_plus
from cryptography.fernet import Fernet
import secrets

with open("config.json") as f:
    cfg = json.load(f)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

username = quote_plus(cfg["mongo_username"])
password = quote_plus(cfg["mongo_password"])

mongo_uri = f"mongodb+srv://{username}:{password}@remote-login.x2yhnuf.mongodb.net/?retryWrites=true&w=majority&appName=Remote-login"
client = MongoClient(mongo_uri)
db = client["cookie_store"]
collection = db["cookies"]

fernet = Fernet(cfg["encryption_key"].encode())

session_ip_map = {}

def wait_for_port(host, port, timeout=60):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=10):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(2)
    return False

def wait_for_vnc_ready(ip, timeout=60):
    url = f"https://{ip}:443/vnc.html"
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    return False

@app.post("/session")
def create_session():
    try:
        session_id = str(uuid4())
        public_ip = launch_vm.launch_instance(session_id)
        session_ip_map[session_id] = public_ip

        #is_port_ready = wait_for_port(public_ip, 443, timeout=300)
        is_port_ready = True
        is_vnc_ready = wait_for_vnc_ready(public_ip,timeout=300)
        if not is_port_ready:
            raise HTTPException(status_code=504, detail="VM launched but port did not become ready in time.")
        if not is_vnc_ready:
            raise HTTPException(status_code=504, detail="VM launched but noVNC did not become ready in time.")
        
        return{"session_id":session_id, "ip":public_ip, "url":f"https://{public_ip}:443/vnc.html"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.delete("/session/{session_id}")
def terminate_session(session_id:str):
    try:
        launch_vm.terminate_instance(session_id)
        session_ip_map.pop(session_id, None)
        return {"message": f"Session {session_id} terminated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/extract_cookies")
def extract_cookies(ip: str, domain: str):
    try:
        url = f"http://{ip}:8080/fetch_cookies?domain={domain}"
        response = requests.get(url,timeout=15)
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="VM responded with error while fetching cookies.")
        
        cookies = response.json().get("cookies")
        if not cookies:
            raise HTTPException(status_code=500, detail="No cookies found in response.")
        
        cookies_str = json.dumps(cookies)
        encrypted = fernet.encrypt(cookies_str.encode())

        access_token = secrets.token_urlsafe(32)
        session_id = [k for k, v in session_ip_map.items() if v == ip][0]

        # Store in DB
        collection.insert_one({
            "domain": domain,
            "session_id": session_id,
            "encrypted_cookies": encrypted.decode(),
            "access_token": access_token
        })
        
        return {
            "access_token": access_token,
            "cookies": cookies
        }
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=504, detail=f"Failed to connect to VM: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/cookies")
def get_cookies(session_id: str, access_token: str):
    try:
        doc = collection.find_one({
            "session_id": session_id,
            "access_token": access_token
        })
        if not doc:
            raise HTTPException(status_code=403, detail="Inavlid session ID or access token.")

        encrypted = doc["encrypted_cookies"].encode()
        decrypted = fernet.decrypt(encrypted).decode()
        cookies = json.loads(decrypted)

        return {"cookies": cookies}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))