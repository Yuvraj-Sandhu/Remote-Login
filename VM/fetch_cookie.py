from fastapi import FastAPI, HTTPException, Query
import asyncio
import websockets
import json
import requests

app = FastAPI()

@app.get("/fetch_cookies")
async def fetch_cookies(domain: str = Query(...)):
    try:
        cookies = await get_cookies_for_domain(domain)
        return {"cookies":cookies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_cookies_for_domain(target_domain):
    # Fetch list of open tabs from Chrome
    tabs = requests.get('http://localhost:9222/json').json()

    ws_url = None
    for tab in tabs:
        if 'url' in tab and target_domain in tab['url']:
            ws_url = tab['webSocketDebuggerUrl']
            break
    if not ws_url:
        raise Exception(f"No tab open for domain: {target_domain}")

    async with websockets.connect(ws_url) as websocket:
        msg_id = 1
        request = {
            "id": msg_id,
            "method": "Network.getAllCookies"
        }

        await websocket.send(json.dumps(request))
        response = await websocket.recv()
        result = json.loads(response)

        raw_cookies = result.get("result", {}).get("cookies", [])
        filtered = {
                c["name"]: c["value"]
                for c in raw_cookies
                if target_domain in c["domain"]
        }

        return filtered