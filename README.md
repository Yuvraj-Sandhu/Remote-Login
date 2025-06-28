# Remote Login App

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Available-brightgreen)](https://remotelogin.vercel.app/)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-blue)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/Frontend-React%2018-blue)](https://reactjs.org/)
[![Oracle Cloud](https://img.shields.io/badge/Cloud-Oracle%20OCI-orange)](https://www.oracle.com/cloud/)
[![MongoDB Atlas](https://img.shields.io/badge/Database-MongoDB%20Atlas-green)](https://www.mongodb.com/cloud/atlas)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Secure, ephemeral remote‑desktop sessions for cookie‑based authentication**  
> Let users log into real third‑party sites in isolated VMs, capture & encrypt cookies, then auto‑teardown everything.

---

## Live Demo

- **Full end‑to‑end** (React on Vercel + FastAPI on Render + Oracle OCI):  
  https://remotelogin.vercel.app/

---

## Features

- **Isolated Browser Sessions**: Launch per‑user Oracle OCI VMs running LXDE + Chrome + noVNC.  
- **Secure VNC over HTTPS**: Caddy + Cloudflare reverse proxy on custom subdomains (`session-XXXXXXXX.remote-login.org`).  
- **Cookie Extraction**: Chrome DevTools Protocol inside each VM; backend fetches via WebSocket.  
- **Encryption & Storage**: Fernet‑encrypted cookies saved in MongoDB Atlas, retrievable via short‑lived token.  
- **Ephemeral Infrastructure**: VMs and DNS records auto‑destroyed on demand or after 15 min.  
- **Rate Limiting**: `slowapi` enforces creation/extraction quotas per IP to prevent abuse.  
- **CORS / Origin Lockdown**: Only the React app domain may call the API.

---

## Architecture

```text
User Browser (React SPA)
       │ POST /session
       ▼
FastAPI Backend (Render.com)
       │ launches VM via OCI SDK
       │ creates Cloudflare A record
       ▼
Oracle OCI VM (“session-XXXXXXXX.remote-login.org”)
  ├─ Xvfb + LXDE + Google Chrome
  ├─ noVNC proxy on :6080
  ├─ Caddy reverse proxy on :443 → :6080
  └─ FastAPI “fetch_cookies” service on :8080
       │ GET /fetch_cookies?domain=example.com
       ▼
Chrome DevTools Protocol → extract cookies
       │ POST back to main backend /extract_cookies
       ▼
MongoDB Atlas (encrypted cookie store)
```

---

## Tech Stack

| Layer            |Technology                              |
|------------------|----------------------------------------|
| Frontend	       | React 18, Axios, Vite                  |
| Backend	       | FastAPI, Uvicorn, slowapi(rate‑limit)  |
| Infrastructure   | Oracle OCI Python SDK                  |
| VNC Proxy	       | noVNC + Websockify                     |
| Reverse Proxy	   | Caddy (automatic HTTPS via Cloudflare) |
| DNS & CDN	       | Cloudflare DNS + Proxy                 |
| Database	       | MongoDB Atlas                          |
| Encryption 	   | Python cryptography Fernet             |

---

## Getting Started

### 1. Prerequisites

- Node.js ≥ 16

- Python 3.10+

- Oracle OCI credentials

- MongoDB Atlas URI with user & password

- Cloudflare API token & Zone ID

Create a `config.json` in your backend root:

```json
{
  "mongo_username": "...",
  "mongo_password": "...",
  "encryption_key": "<your‑fernet‑key‑here>",
  "cloudflare_token": "...",
  "cloudflare_zone_id": "...",
  "ssh_key_path": "~/.ssh/id_rsa.pub",
  "compartment_id": "...",
  "availability_domain": "...",
  "shape": "VM.Standard.E3.Flex",
  "image_id": "...",
  "subnet_id": "..."
}
```

### 2. Frontend

```bash
cd frontend
npm install
npm start
```

Available at http://localhost:3000

### 3. Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Available at http://localhost:8000

---

## Project Structure

```
remote-login/
│
│
├── backend/              # FastAPI backend
│ ├── main.py             # Main FastAPI app
│ ├── launch_vm.py        # Oracle Cloud VM orchestration
│ ├── validate_flow.py    # Validation script
│ └── requirements.txt    # Python dependencies
│
│
├── frontend/           # React frontend
│ ├── public/           # Static assets
│ ├── src/              # Source code
│ │ ├── App.js          # Main React component
│ │ └── App.css         # Styling
│ └── package.json      # Frontend dependencies
│
│
├── vm/                 # VM-side code
│ └── fetch_cookie.py   # Runs inside each VM instance
│
│
├── LICENSE             # MIT License
├── README.md           # Project documentation (this file)
└── design_notes.md     # Design docs
```

---

## API Reference

### POST /session

Create a new remote browser session.

**Response:**
```json
{
  "session_id": "UUID",
  "ip": "VM_PUBLIC_IP",
  "url": "https://session-XXXXXXXX.remote-login.org/vnc.html"
}
```

### Delete /session/{session_id}

Tear down VM & DNS record.

### GET /extract_cookies?ip=&domain=
Fetch cookies from VM’s FastAPI, encrypt & store.

**Response:**
```
{
  "session_id": "UUID",
  "access_token": "short_token",
  "cookies": { "name": "value", … }
}
```

### GET /cookies?session_id=&access_token=
Retrieve encrypted cookies from DB.

---

## Cleanup & Auto‑Termination

- Each VM runs (sleep 900; sudo shutdown -h now) & in its startup script.

- Backend also spawns a background thread to terminate VM and delete Cloudflare DNS after 15 min.

 ---

 ## Observability & Monitoring
Logs: session creation, DNS record IDs, VM lifecycle, cookie extraction.

Metrics: extend with Prometheus/Grafana (e.g. active sessions, errors per minute).

Cloud Dashboard: view ephemeral VMs and deleted resources.

---

## Design Trade-offs

| Aspect           | Decision                  | Trade-off                                      |
|------------------|---------------------------|-----------------------------------------------|
| VM vs. Container | VM for simpler PoC        | Containers are faster to start and stop, but add networking complexity (overlay, orchestration).    |
| Cloud Provider   |Oracle cloud infrastructure| Free or lower-cost credits for PoC. AWS or GCP might have more automation tools but higher cost.       |
| Database         | MongoDB Atlas             | Easy JSON storage for unstructured cookie data; a SQL DB could add stricter schema and ACID guarantees but more overhead.         |
| Remote Access    | noVNC over HTTPS          | Easier than setting up WebRTC or SSH tunneling, slightly higher latency than native solutions.         |
| Cookie Extraction| Chrome DevTools           | Simple, reliable and easier than hard-coding open tabs in script. Headless scraping tools or proxies could offer more stealth but add complexity.   |
| Dynamic DNS      | Cloudflare subdomains     | Rapid SSL + DNS management, custom certs with static IPs could remove propagation delays but are harder to automate.             |
| Auto Termination | Handled by backend background processes  | Could use instance metadata or serverless for reliability |

---

## Design Notes

See [design_notes.pdf](design_notes.pdf) for deeper rationale, architecture, and alternate approaches.

---

## Security Considerations

- Never capture user credentials.

- Encrypt cookies at rest; keys kept out of code.

- Rate‑limit all endpoints.

- Restrict CORS to only React app’s origin.

- Use least‑privilege IAM roles for OCI.

---

## Additional Resources

- [React Documentation](https://react.dev/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [MongoDB Atlas Docs](https://www.mongodb.com/docs/atlas/)
- [Oracle Cloud Infrastructure Docs](https://docs.oracle.com/en-us/iaas/Content/home.htm)
- [Cloudflare API Docs](https://developers.cloudflare.com/api/)
- [noVNC Docs](https://github.com/novnc/noVNC)
- [Caddy Server Docs](https://caddyserver.com/docs/)
- [Cryptography Python Package](https://cryptography.io/en/latest/)
- [Uvicorn Docs](https://www.uvicorn.org/)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---