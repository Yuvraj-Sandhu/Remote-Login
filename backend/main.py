from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import launch_vm
from uuid import uuid4
import time, socket


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

session_ip_map = {}

def wait_for_port(host, port, timeout=60):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=5):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(2)
    return False

@app.post("/session")
def create_session():
    try:
        session_id = str(uuid4())
        public_ip = launch_vm.launch_instance(session_id)
        session_ip_map[session_id] = public_ip

        is_ready = wait_for_port(public_ip, 6080, timeout=90)
        if not is_ready:
            raise HTTPException(status_code=504, detail="VM launched but noVNC did not become ready in time.")
        
        return{"session_id":session_id, "ip":public_ip, "url":f"http://{public_ip}:6080/vnc.html"}
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