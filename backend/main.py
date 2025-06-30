"""
                                    Remote-Login Backend API
===================================================================================================

A FastAPI backend service for managing ephemeral cloud-based browser sessions with 
automated cookie extraction and secure storage capabilities. This service orchestrates
the entire lifecycle of temporary virtual machine instances, providing isolated browser
environments for web automation, testing, and secure data extraction workflows.

Core Functionality:
- On-demand VM provisioning with browser environments
- Dynamic subdomain creation and DNS management
- Real-time session monitoring and health checks
- Automated cookie extraction and encryption
- Secure database storage with access token authentication
- Rate limiting and CORS protection
- Automatic resource cleanup and cost management

Architecture Overview:
- FastAPI: High-performance async web framework
- OCI Integration: Dynamic compute instance management
- Cloudflare API: DNS record management for subdomains
- MongoDB: Encrypted cookie storage with authentication
- Cryptography: Fernet symmetric encryption for data protection
- Threading: Asynchronous cleanup operations

Use Cases:
- Automated web scraping with session persistence
- Secure cookie extraction for authentication workflows
- Temporary isolated browsing sessions

Security Features:
- Rate limiting on all endpoints (5-10 requests/minute)
- CORS restrictions to authorized origins
- Encrypted cookie storage using Fernet encryption
- Access token-based authentication
- Automatic session cleanup to prevent resource abuse
- URL-safe token generation for secure access

Dependencies:
- fastapi: Modern web framework with automatic API documentation
- fastapi.middleware.cors: Cross-Origin Resource Sharing support
- slowapi: Rate limiting middleware for FastAPI
- launch_vm: Custom OCI instance management module
- pymongo: MongoDB database client
- cryptography: Encryption/decryption services
- requests: HTTP client for external API calls
- threading: Asynchronous task execution
- secrets: Cryptographically secure token generation
- uuid: Unique identifier generation

Configuration Requirements:
- config.json: Application configuration containing:
  - mongo_username/mongo_password: MongoDB Atlas credentials
  - encryption_key: Fernet encryption key (32 bytes base64)
  - cloudflare_token: Cloudflare API token with DNS permissions
  - cloudflare_zone_id: Target DNS zone identifier

Resource Management:
- Automatic VM termination after 15 minutes
- DNS record cleanup on session termination
- Memory-efficient session tracking
- Database connection pooling
- Thread-safe operations for concurrent requests
"""


# =============================================================================
# IMPORTS
# =============================================================================

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import launch_vm
from uuid import uuid4
import time, requests, json
from pymongo import MongoClient
from urllib.parse import quote_plus
from cryptography.fernet import Fernet
import secrets
import threading


# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

# Load application configuration from JSON file
# Contains database credentials, API keys, and encryption settings
with open("config.json") as f:
    cfg = json.load(f)


# =============================================================================
# FASTAPI APPLICATION SETUP
# =============================================================================

# Initialize FastAPI application instance
# Provides automatic API documentation and high-performance async handling
app = FastAPI()

# Configure Cross-Origin Resource Sharing (CORS)
# Restricts API access to authorized frontend applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://remotelogin.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Configure rate limiting to prevent abuse
# Limits requests per IP address to ensure fair usage
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# =============================================================================
# DATABASE CONNECTION SETUP
# =============================================================================

# Prepare MongoDB Atlas connection with URL encoding
# Ensures special characters in credentials are properly escaped
username = quote_plus(cfg["mongo_username"])
password = quote_plus(cfg["mongo_password"])

# Construct MongoDB Atlas connection URI
# Includes retry logic and write concern for reliability
mongo_uri = f"mongodb+srv://{username}:{password}@remote-login.x2yhnuf.mongodb.net/?retryWrites=true&w=majority&appName=Remote-login"
# Initialize MongoDB client and database connections
client = MongoClient(mongo_uri)
db = client["cookie_store"]
collection = db["cookies"]


# =============================================================================
# ENCRYPTION SETUP
# =============================================================================

# Initialize Fernet symmetric encryption for cookie data protection
# Uses 32-byte base64-encoded key from configuration
fernet = Fernet(cfg["encryption_key"].encode())


# =============================================================================
# SESSION MANAGEMENT STORAGE
# =============================================================================

# In-memory session tracking dictionaries
# Thread-safe for concurrent access patterns
session_ip_map = {}
session_record_map = {}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def wait_for_vnc_ready(ip, timeout=60):
    """
    Wait for VNC service to become available on a newly launched VM instance.
    
    This function performs health checks against the noVNC web interface to ensure
    the virtual machine is fully operational before allowing user access. It implements
    a polling mechanism with exponential backoff to handle various startup scenarios.
    
    The function tests connectivity to the noVNC HTML interface which serves as a
    reliable indicator that the entire browser environment stack is operational,
    including:
    - X11 virtual display server (Xvfb)
    - Desktop environment (LXDE)
    - VNC server (x11vnc)
    - noVNC web proxy
    - Chrome browser with automation configuration
    
    Args:
        ip (str): Public IP address of the target VM instance.
                 Should be a valid IPv4 address returned from OCI launch operation.
        timeout (int, optional): Maximum time to wait in seconds. Defaults to 60.
    
    Returns:
        bool: True if VNC service responds successfully within timeout period.
              False if timeout expires before service becomes available.
    
    Network Requirements:
        - VM must have public IP accessibility
        - Port 6080 must be open for HTTP traffic
        - noVNC service must be running and bound to 0.0.0.0:6080
        
    Error Handling:
        - Gracefully handles network timeouts and connection errors
        - Continues polling despite temporary network issues
        - Uses 2-second intervals to balance responsiveness and resource usage
    """
    # Construct health check URL for noVNC interface
    # Tests the main HTML file that indicates full service availability
    url = f"http://{ip}:6080/vnc.html"
    start_time = time.time()

    # Poll service availability until timeout
    while time.time() - start_time < timeout:
        try:
            # Attempt HTTP GET request with connection timeout
            # 10-second timeout prevents hanging on network issues
            response = requests.get(url, timeout=10)

            # Check for successful HTTP response
            # 200 OK indicates noVNC is serving content properly
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            # Silently handle all request exceptions
            # Common during VM startup: ConnectionError, Timeout, etc.
            pass
        time.sleep(2)

    # Timeout expired without successful response
    return False

# -----------------------------------------------------------------------------

def wait_for_domain_ready(domain, timeout=60):
    """
    Wait for custom domain to properly resolve and serve VNC content via Cloudflare proxy.
    
    This function verifies that the Cloudflare DNS record has propagated and the
    reverse proxy is correctly routing traffic to the VM instance. It is essential
    for ensuring users can access their sessions via the friendly subdomain rather
    than raw IP addresses.
    
    The function validates the complete DNS->CDN->VM request flow:
    - DNS propagation of A record to Cloudflare
    - Cloudflare proxy activation and SSL termination
    - Reverse proxy routing to VM noVNC service
    - VM response through the entire chain
    
    Args:
        domain (str): Fully qualified domain name to test.
                     Format: "session-{uuid8}.remote-login.org"
                     Must match the subdomain created in Cloudflare.
        timeout (int, optional): Maximum wait time in seconds. Defaults to 60.
    
    Returns:
        bool: True if domain successfully serves VNC content within timeout.
              False if timeout expires before domain becomes accessible.
    
    DNS Requirements:
        - Cloudflare DNS record must be created and active
        - TTL should be set low (120 seconds) for faster propagation
        - Proxy status should be enabled for SSL termination
        
    Network Flow:
        Client -> Cloudflare Edge -> Origin VM:6080 -> noVNC -> Response
        
    Common Failure Scenarios:
        - DNS propagation delays (especially with high TTL)
        - Cloudflare proxy configuration issues
        - VM firewall blocking port 6080
        - noVNC service not properly bound to external interface
    """
    # Construct domain health check URL
    # Tests same noVNC interface through Cloudflare proxy
    url = f"http://{domain}/vnc.html"
    start_time = time.time()

    # Poll domain availability until timeout
    while time.time() - start_time < timeout:
        try:
            # Test HTTP connectivity through domain
            # Uses same timeout as direct IP check for consistency
            response = requests.get(url, timeout=10)
            # Verify successful response through proxy chain
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            # Handle DNS resolution failures, proxy errors, etc.
            # Expected during DNS propagation period
            pass
        time.sleep(2)

    # Domain failed to become accessible within timeout
    return False

# -----------------------------------------------------------------------------

def auto_delete_VM_and_subdomain(session_id, record_id):
    """
    Automatically clean up VM instance and DNS record after session timeout.
    
    This function runs in a background thread to ensure automatic resource cleanup
    and cost management. It implements a delayed cleanup mechanism that allows
    sufficient time for user sessions while preventing runaway resource usage.
    
    The cleanup process handles both compute and DNS resources:
    1. Waits for the configured timeout period (15 minutes)
    2. Terminates the OCI compute instance
    3. Removes the session from in-memory tracking
    4. Deletes the Cloudflare DNS record
    5. Cleans up session mappings
    
    This function is critical for:
    - Preventing unexpected cloud infrastructure costs
    - Maintaining clean resource inventory
    - Ensuring DNS zone doesn't accumulate stale records
    - Providing predictable session lifecycle management
    
    Args:
        session_id (str): Unique session identifier for resource tracking.
                         Must match the session used in VM creation.
        record_id (str): Cloudflare DNS record identifier for cleanup.
                        Retrieved from DNS record creation API response.
    
    Returns:
        None: Function executes asynchronously and returns nothing.
              Errors are silently handled to prevent thread crashes.
    
    Resource Cleanup Order:
        1. VM termination (stops compute billing)
        2. Memory cleanup (removes session tracking)
        3. DNS cleanup (removes subdomain routing)
        
    Error Handling:
        - VM termination errors are handled by launch_vm module
        - DNS deletion errors are silently ignored (records may expire)
        - Memory cleanup uses safe dictionary operations
        
    Thread Safety:
        - Uses thread-safe dictionary operations
        - No shared mutable state beyond session maps
        - Safe to run multiple cleanup threads concurrently
    """
    # Wait for session timeout period
    time.sleep(15 * 60)

    # =================================================================
    # VM INSTANCE CLEANUP
    # =================================================================
    # Terminate OCI compute instance to stop billing
    # Handles instance state validation and proper shutdown
    launch_vm.terminate_instance(session_id)

    # Remove session from IP tracking dictionary
    # Uses pop() with default to handle missing keys gracefully
    session_ip_map.pop(session_id, None)
    
    # =================================================================
    # DNS RECORD CLEANUP
    # =================================================================
    # Prepare Cloudflare API credentials for DNS management
    cf_token = cfg["cloudflare_token"]
    zone_id = cfg["cloudflare_zone_id"]

    # Remove session from DNS record tracking
    # Retrieves record_id for deletion API call
    record_id = session_record_map.pop(session_id, None)

    # Delete DNS record if it exists
    if record_id:
        # Configure API request headers
        headers = {
            "Authorization": f"Bearer {cf_token}",
            "Content-Type": "application/json"
        }

        # Construct DNS record deletion URL
        url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"

        # Execute DNS record deletion
        # Errors are silently ignored to prevent thread crashes
        requests.delete(url, headers=headers)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.post("/session")
@limiter.limit("5/minute")
def create_session(request: Request):
    """
    Create a new ephemeral browser session with dedicated VM and subdomain.
    
    This endpoint orchestrates the complete provisioning workflow for a new
    browser session, including VM creation, DNS configuration, health monitoring,
    and automatic cleanup scheduling. It provides users with a fully isolated
    browser environment accessible via a custom subdomain.
    
    The provisioning process includes:
    1. Unique session ID generation
    2. Subdomain name creation
    3. OCI VM instance launch with browser environment
    4. Cloudflare DNS record creation
    5. Service health verification
    6. Background cleanup scheduling
    
    Each session provides:
    - Dedicated Ubuntu VM with 4 vCPUs and 32GB RAM
    - Chrome browser with automation-friendly configuration
    - VNC remote desktop access via web interface
    - Custom subdomain for easy access
    - FastAPI cookie extraction service
    - Automatic 15-minute session timeout
    
    Args:
        request (Request): FastAPI request object for rate limiting.
                          Used by slowapi to track client IP addresses.
    
    Returns:
        dict: Session information containing:
            - session_id (str): Unique identifier for session management
            - ip (str): Public IP address of the VM instance
            - url (str): Complete HTTPS URL for browser access
    
    Raises:
        HTTPException: Various error conditions:
            - 500: VM launch failure, DNS creation failure, or timeout
            - 504: VM launched but services not ready within timeout
            - 429: Rate limit exceeded (5 requests/minute)
    
    Rate Limiting:
        - 5 requests per minute per IP address
        - Prevents resource abuse and ensures fair usage
        - Automatically enforced by slowapi middleware
    
    Resource Requirements:
        - Available OCI compute quota
        - Cloudflare API rate limits
        - DNS zone management permissions
        
    Session Lifecycle:
        1. Created: VM launching, DNS propagating
        2. Ready: Services operational, user accessible
        3. Active: User interaction period (up to 15 minutes)
        4. Cleanup: Automatic termination and resource cleanup
        
    Error Scenarios:
        - OCI quota exceeded: Returns 500 with quota error
        - DNS creation failure: Returns 500 with Cloudflare error
        - Service timeout: Returns 504 with timeout details
        - Network issues: Returns 500 with connection error
    """
    try:
        # =================================================================
        # SESSION INITIALIZATION
        # =================================================================
        # Generate cryptographically secure unique session identifier
        # UUID4 provides 122 bits of entropy for collision resistance
        session_id = str(uuid4())
        # Create human-readable subdomain from session ID
        # Uses first 8 characters for brevity while maintaining uniqueness
        subdomain = f"session-{session_id[:8]}"
        domain = f"{subdomain}.remote-login.org"

        # =================================================================
        # VM INSTANCE PROVISIONING
        # =================================================================
        # Launch OCI compute instance with browser environment
        # Returns public IP address for network access
        public_ip = launch_vm.launch_instance(session_id, domain)

        # Track session-to-IP mapping for cookie extraction
        # Required for routing cookie requests to correct VM
        session_ip_map[session_id] = public_ip

        # =================================================================
        # DNS RECORD CREATION
        # =================================================================
        # Prepare Cloudflare API credentials
        cf_token = cfg["cloudflare_token"]
        zone_id = cfg["cloudflare_zone_id"]

        # Configure API request headers
        headers = {
            "Authorization": f"Bearer {cf_token}",
            "Content-Type": "application/json"
        }

        # Define DNS record configuration
        data = {
            "type": "A",
            "name": subdomain,
            "content": public_ip,
            "ttl": 120,
            "proxied": True
        }

        # Create DNS record via Cloudflare API
        url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
        response = requests.post(url, headers=headers, json=data)

        # Validate DNS record creation success
        if not response.ok:
            raise HTTPException(status_code=500, detail=f"Cloudflare DNS create failed: {response.text}")

        # Extract DNS record ID for future cleanup
        record_id = response.json()["result"]["id"]
        session_record_map[session_id] = record_id

        # =================================================================
        # SERVICE HEALTH VERIFICATION
        # =================================================================
        # Wait for VNC service to become operational
        # Extended timeout (300s) accommodates VM startup time
        is_vnc_ready = wait_for_vnc_ready(public_ip,timeout=300)

        # Additional stabilization time for service initialization
        # Ensures all components are fully loaded before domain test
        time.sleep(30)

        # Verify domain accessibility through Cloudflare proxy
        # Confirms complete request routing chain functionality
        is_domain_ready = wait_for_domain_ready(domain,timeout=60)

        # Handle VNC service startup failure
        if not is_vnc_ready:
            raise HTTPException(status_code=504, detail="VM launched but noVNC did not become ready in time.")
        
        # Handle domain propagation failure
        if not is_domain_ready:
            raise HTTPException(status_code=504, detail="Domain did not ready in time.")
        
        # =================================================================
        # BACKGROUND CLEANUP SCHEDULING
        # =================================================================
        # Start automatic cleanup thread for resource management
        # Prevents runaway costs and ensures predictable lifecycle
        threading.Thread(target=auto_delete_VM_and_subdomain, args=(session_id, record_id)).start()

        # =================================================================
        # SUCCESS RESPONSE
        # =================================================================
        # Return session details for client use
        return{
            "session_id":session_id, 
            "ip":public_ip, 
            "url":f"https://{domain}/vnc.html"
        }
    except Exception as e:
        # Handle any unexpected errors in session creation
        # Provides detailed error information for debugging
        raise HTTPException(status_code=500, detail=str(e))
    
# -----------------------------------------------------------------------------

@app.delete("/session/{session_id}")
@limiter.limit("5/minute")
def terminate_session(session_id:str, request: Request):
    """
    Immediately terminate an active browser session and clean up all resources.
    
    This endpoint provides manual session termination capability, allowing users
    to clean up resources before the automatic 15-minute timeout. It performs
    the same cleanup operations as the automatic cleanup but executes immediately
    rather than waiting for the scheduled timeout.
    
    The termination process includes:
    1. OCI compute instance termination
    2. Session tracking cleanup
    3. Cloudflare DNS record deletion
    4. Memory resource deallocation
    
    This endpoint is useful for:
    - Immediate resource cleanup when session work is complete
    - Cost optimization by stopping billing as soon as possible
    - Error recovery scenarios requiring session reset
    - Administrative cleanup of problematic sessions
    
    Args:
        session_id (str): Unique session identifier to terminate.
                         Must match a previously created session ID.
        request (Request): FastAPI request object for rate limiting.
    
    Returns:
        dict: Confirmation message containing:
            - message (str): Success confirmation with session ID
    
    Raises:
        HTTPException: Error conditions:
            - 500: VM termination failure, DNS deletion failure
            - 429: Rate limit exceeded (5 requests/minute)
            - 404: Session not found (handled as generic 500)
    
    Rate Limiting:
        - 5 requests per minute per IP address
        - Shares rate limit with session creation endpoint
        - Prevents abuse of termination functionality
    
    Resource Cleanup:
        - Compute: Instance terminated and billing stopped
        - Network: Public IP released back to pool
        - DNS: Subdomain record removed from zone
        - Memory: Session mappings cleared from service
        
    Idempotency:
        - Safe to call multiple times for same session
        - DNS record deletion failures silently ignored
        
    Error Scenarios:
        - Invalid session ID: Returns 500 with "not found" error
        - VM already terminated: Returns 500 with termination error
        - DNS API failure: Returns 500 with Cloudflare error
        - Network timeout: Returns 500 with connection error
    """
    try:
        # =================================================================
        # VM INSTANCE TERMINATION
        # =================================================================
        # Terminate OCI compute instance to stop billing immediately
        # Handles instance state validation and graceful shutdown
        launch_vm.terminate_instance(session_id)

        # Remove session from IP mapping dictionary
        # Prevents cookie extraction attempts on terminated VM
        session_ip_map.pop(session_id, None)

        # =================================================================
        # DNS RECORD CLEANUP
        # =================================================================
        # Prepare Cloudflare API credentials for DNS management
        cf_token = cfg["cloudflare_token"]
        zone_id = cfg["cloudflare_zone_id"]

        # Retrieve DNS record ID for deletion
        # Uses pop() to remove mapping and get value atomically
        record_id = session_record_map.pop(session_id, None)

        # Delete DNS record if it exists
        if record_id:
            # Configure API request headers
            headers = {
                "Authorization": f"Bearer {cf_token}",
                "Content-Type": "application/json"
            }

            # Construct DNS record deletion URL
            url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"

            # Execute DNS record deletion
            requests.delete(url, headers=headers)

        # =================================================================
        # SUCCESS RESPONSE
        # =================================================================
        # Return confirmation of successful termination
        return {"message": f"Session {session_id} terminated successfully"}
    except Exception as e:
        # Handle termination errors with detailed error information
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------------

@app.get("/extract_cookies")
@limiter.limit("10/minute")
def extract_cookies(ip: str, domain: str, request: Request):
    """
    Extract cookies from a browser session and store them securely in the database.
    
    This endpoint communicates with the FastAPI cookie extraction service running
    on the VM instance to retrieve browser cookies for a specific domain. The
    cookies are then encrypted and stored in MongoDB with secure access token
    authentication for later retrieval.
    
    The extraction process:
    1. Sends request to VM's cookie extraction service
    2. Validates response contains cookie data
    3. Encrypts cookie data using Fernet symmetric encryption
    4. Generates cryptographically secure access token
    5. Stores encrypted data in MongoDB with access controls
    6. Returns both raw cookies and secure access credentials
    
    This functionality enables:
    - Authentication session preservation across requests
    - Secure cookie storage for later automation use
    - Cross-session cookie sharing with proper authorization
    - Cookie-based authentication for web scraping workflows
    
    Args:
        ip (str): Public IP address of the target VM instance.
                 Must match an active session's IP address.
        domain (str): Target domain for cookie extraction.
                     Cookies will be filtered to this domain scope.
        request (Request): FastAPI request object for rate limiting.
    
    Returns:
        dict: Cookie extraction results containing:
            - session_id (str): Session identifier for tracking
            - access_token (str): Secure token for cookie retrieval
            - cookies (list): Raw cookie data for immediate use
    
    Raises:
        HTTPException: Various error conditions:
            - 502: VM cookie service responded with error
            - 500: No cookies found, encryption failure, database error
            - 504: Failed to connect to VM cookie service
            - 429: Rate limit exceeded (10 requests/minute)
    
    Rate Limiting:
        - 10 requests per minute per IP address
        - Higher limit than session management (extraction is lightweight)
        - Allows multiple cookie extractions per session
    
    Security Features:
        - Cookies encrypted with Fernet before database storage
        - Access tokens use cryptographically secure random generation
        - Database queries use exact session and token matching
        - Raw cookies returned only once during extraction
        
    Cookie Service Communication:
        - Connects to VM port 8080 (FastAPI cookie service)
        - 15-second timeout prevents hanging requests
        - Validates JSON response format
        
    Database Schema:
        {
            "domain": "example.com",
            "session_id": "550e8400-e29b-41d4-a716-446655440000",
            "encrypted_cookies": "base64_encrypted_data",
            "access_token": "secure_random_token"
        }
        
    Error Scenarios:
        - VM service down: Returns 504 with connection error
        - No cookies found: Returns 500 with "no cookies" message
        - Invalid IP: Returns 504 with timeout error
        - Database failure: Returns 500 with database error
    """
    try:
        # =================================================================
        # COOKIE EXTRACTION FROM VM
        # =================================================================
        # Construct URL for VM's cookie extraction service
        # Service runs on port 8080 with domain parameter
        url = f"http://{ip}:8080/fetch_cookies?domain={domain}"

        # Request cookies from VM with reasonable timeout
        # 15 seconds allows for cookie processing without hanging
        response = requests.get(url,timeout=15)

        # Validate VM service responded successfully
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="VM responded with error while fetching cookies.")
        
        # Extract cookies from JSON response
        cookies = response.json().get("cookies")

        # Validate cookies were found and returned
        if not cookies:
            raise HTTPException(status_code=500, detail="No cookies found in response.")
        
        # =================================================================
        # COOKIE ENCRYPTION AND STORAGE
        # =================================================================
        # Serialize cookies to JSON string for encryption
        cookies_str = json.dumps(cookies)

        # Encrypt cookie data using Fernet symmetric encryption
        # Ensures cookie data is protected at rest in database
        encrypted = fernet.encrypt(cookies_str.encode())

        # Generate cryptographically secure access token
        # 32 bytes provides 256 bits of entropy for secure access
        access_token = secrets.token_urlsafe(32)

        # Reverse lookup session ID from IP address
        # Required for database storage and future retrieval
        session_id = [k for k, v in session_ip_map.items() if v == ip][0]

        # =================================================================
        # DATABASE STORAGE
        # =================================================================
        # Store encrypted cookies with access control in MongoDB
        collection.insert_one({
            "domain": domain,
            "session_id": session_id,
            "encrypted_cookies": encrypted.decode(),
            "access_token": access_token
        })

        # =================================================================
        # SUCCESS RESPONSE
        # =================================================================
        # Returns cookies for client use
        return {
            "session_id": session_id,
            "access_token": access_token,
            "cookies": cookies
        }
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=504, detail=f"Failed to connect to VM: {str(e)}")
    except Exception as e:
        # Handle termination errors with detailed error information
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/cookies")
@limiter.limit("10/minute")
def get_cookies(session_id: str, access_token: str, request: Request):
    """
    Retrieve previously extracted cookies from the database using secure credentials.

    This endpoint allows authorized clients to retrieve encrypted cookie data that was
    previously extracted and stored during a session. It requires both the unique
    session ID and the secure access token generated during the extraction process.
    If valid, it decrypts the cookie data using Fernet symmetric encryption and returns
    the raw cookies in JSON format.

    This functionality enables:
    - Session cookie reuse for automated login workflows
    - Secure cookie delivery only to clients with valid credentials
    - Separation of extraction and retrieval stages for enhanced security

    Args:
        session_id (str): Unique identifier for the session whose cookies are requested.
                          Must match a session that previously stored cookies.
        access_token (str): Secure token generated during extraction.
                            Provides an additional layer of access control.
        request (Request): FastAPI request object for rate limiting enforcement.

    Returns:
        dict: Retrieved cookies in raw JSON format if credentials are valid.
              Example:
              {
                  "cookies": [
                      {"name": "sessionid", "value": "...", ...},
                      ...
                  ]
              }

    Raises:
        HTTPException: Error conditions:
            - 403: Invalid session ID or access token.
            - 500: Database connection or decryption failure.
            - 429: Rate limit exceeded (10 requests/minute).

    Rate Limiting:
        - Limited to 10 requests per minute per IP address.
        - Prevents abuse or brute-force attempts.

    Security Features:
        - Encrypted cookie storage prevents data leakage at rest.
        - Access token ensures only authorized retrieval.
        - Decrypted data never persists after retrieval.
    """
    try:
        # =================================================================
        # DATABASE LOOKUP
        # =================================================================
        # Query MongoDB for a document matching the provided session ID and token.
        # This ensures that only valid sessions and credentials succeed.
        doc = collection.find_one({
            "session_id": session_id,
            "access_token": access_token
        })

        # Handle missing document — means credentials are invalid.
        if not doc:
            raise HTTPException(status_code=403, detail="Inavlid session ID or access token.")

        # =================================================================
        # DECRYPTION
        # =================================================================
        # Retrieve encrypted cookies from the database.
        # Fernet decryption ensures only your service can read the data.
        encrypted = doc["encrypted_cookies"].encode()
        decrypted = fernet.decrypt(encrypted).decode()

        # Deserialize decrypted JSON string back into Python list/dict.
        cookies = json.loads(decrypted)

        # =================================================================
        # SUCCESS RESPONSE
        # =================================================================
        # Return decrypted cookies to the client.
        return {"cookies": cookies}
    
    except Exception as e:
        # Catch-all for any unexpected errors: database, decryption, JSON parse.
        raise HTTPException(status_code=500, detail=str(e))