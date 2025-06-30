"""
===================================================================================================
                             VM Cookie Extraction Service
===================================================================================================

This FastAPI microservice runs inside each ephemeral VM and connects to the Chrome 
Remote Debugging Protocol to extract cookies for a specified domain. 

It communicates directly with Chrome's DevTools protocol via a WebSocket connection
to retrieve all available cookies, filter them by domain, and return them in a 
JSON response. This isolated design ensures that cookies are extracted securely 
within the disposable VM environment, never exposing raw session data outside the 
intended runtime.

Core Functionality:
- Query open Chrome tabs using the DevTools JSON API
- Locate the WebSocket Debugger URL for the target domain
- Use the Network.getAllCookies DevTools method to retrieve all cookies
- Filter cookies by requested domain and return name/value pairs
- Expose a single FastAPI GET endpoint for remote invocation

Security Considerations:
- Runs only on localhost within the VM; no external inbound access
- Only authorized outer FastAPI backend calls this via internal network
- No persistent storage; all cookies are ephemeral in-memory results
- Supports HTTPS connection to upstream orchestrator only

Example Use Case:
- A user starts a remote browser session via the orchestrator.
- After authenticating on a third-party site, the orchestrator calls this 
  endpoint to extract session cookies.
- The cookies are securely returned, encrypted, and stored for later reuse.

Dependencies:
- fastapi: Lightweight web API framework
- websockets: Async WebSocket client to communicate with Chrome DevTools
- requests: Synchronous HTTP client to query Chrome tabs
- asyncio: For running async event loop with FastAPI

===================================================================================================
"""


# =============================================================================
# IMPORTS
# =============================================================================

from fastapi import FastAPI, HTTPException, Query
import asyncio
import websockets
import json
import requests


# =============================================================================
# FASTAPI APPLICATION SETUP
# =============================================================================

# Initialize the FastAPI application instance.
# This service listens only on localhost inside the VM.
app = FastAPI()


# =============================================================================
# API ENDPOINT: FETCH COOKIES
# =============================================================================
@app.get("/fetch_cookies")
async def fetch_cookies(domain: str = Query(...)):
    """
    Extract cookies for a specified domain from the Chrome browser running in the VM.

    This endpoint accepts a target domain as a query parameter, then:
    1. Queries the local Chrome DevTools API to find open tabs.
    2. Locates the WebSocket Debugger URL for the target domain.
    3. Connects to Chrome DevTools over WebSocket.
    4. Sends a Network.getAllCookies request to fetch all available cookies.
    5. Filters cookies to include only those matching the specified domain.

    Args:
        domain (str): The target domain to filter cookies by.
                      Example: "example.com"

    Returns:
        dict: JSON object with a `cookies` key containing filtered cookies as
              a dictionary of name-value pairs.

    Raises:
        HTTPException: Returns HTTP 500 if any error occurs during the process.
    """
    try:
        cookies = await get_cookies_for_domain(domain)
        return {"cookies":cookies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# UTILITY FUNCTION: GET COOKIES FROM CHROME DEVTOOLS
# =============================================================================

async def get_cookies_for_domain(target_domain):
    """
    Locate the Chrome tab matching the target domain and extract cookies using DevTools.

    Steps:
    1. Fetch the list of open tabs from Chrome DevTools JSON endpoint.
    2. Identify a tab whose URL matches the target domain.
    3. Connect to the tab's WebSocket Debugger URL.
    4. Send a DevTools `Network.getAllCookies` command.
    5. Receive and parse the cookies.
    6. Filter cookies by domain match.

    Args:
        target_domain (str): The domain to filter cookies for.

    Returns:
        dict: Dictionary of cookie name-value pairs for the specified domain.

    Raises:
        Exception: If no matching tab is found or WebSocket communication fails.
    """
    # -------------------------------------------------------------------------
    # STEP 1: Query Chrome DevTools JSON API for open tabs
    # -------------------------------------------------------------------------
    tabs = requests.get('http://localhost:9222/json').json()

    # -------------------------------------------------------------------------
    # STEP 2: Identify tab for the target domain
    # -------------------------------------------------------------------------
    ws_url = None
    for tab in tabs:
        if 'url' in tab and target_domain in tab['url']:
            ws_url = tab['webSocketDebuggerUrl']
            break
    if not ws_url:
        raise Exception(f"No tab open for domain: {target_domain}")
    
    # -------------------------------------------------------------------------
    # STEP 3-6: Connect to DevTools, send request, receive cookies
    # -------------------------------------------------------------------------
    async with websockets.connect(ws_url) as websocket:
        # Prepare DevTools command to get all cookies
        msg_id = 1
        request = {
            "id": msg_id,
            "method": "Network.getAllCookies"
        }

        # Send the request over WebSocket
        await websocket.send(json.dumps(request))

        # Receive the response
        response = await websocket.recv()
        result = json.loads(response)

        # Extract raw cookies from DevTools response
        raw_cookies = result.get("result", {}).get("cookies", [])

        # Filter cookies to include only those for the target domain
        filtered = {
                c["name"]: c["value"]
                for c in raw_cookies
                if target_domain in c["domain"]
        }

        return filtered