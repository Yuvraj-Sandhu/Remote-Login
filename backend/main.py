from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import launch_vm
from uuid import uuid4


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.post("/session")
def create_session():
    try:
        session_id = str(uuid4())
        public_ip = launch_vm.launch_instance(session_id)
        return{"session_id":session_id, "ip":public_ip, "url":f"http://{public_ip}:6080/vnc.html"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.delete("/session/{session_id}")
def terminate_session(session_id:str):
    try:
        launch_vm.terminate_instance(session_id)
        return {"message": f"Session {session_id} terminated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))