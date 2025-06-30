/**
 *                React Frontend for Remote-Login Application
 * ================================================================================================
 * 
 * A React component that provides a user interface for managing remote desktop sessions
 * on cloud VMs, extracting browser cookies from specific domains, and downloading
 * authentication data for automated login workflows.
 * 
 * Features:
 * - Remote VM session management with start/stop functionality
 * - Real-time embedded remote desktop access via iframe
 * - Domain-specific cookie extraction from remote browser
 * - Secure session and access token management
 * - Cookie data export with session credentials
 * - Historical cookie retrieval using past session credentials
 * - Comprehensive loading states and user feedback
 * 
 * Architecture:
 * - Uses React hooks for complex state management
 * - Communicates with remote-login backend via REST API
 * - Handles secure session lifecycle management
 * - Provides real-time remote desktop integration
 * - Manages cookie extraction and download workflows
 * 
 * Security Considerations:
 * - Session IDs and access tokens are generated server-side
 * - Cookies are extracted in isolated VM environments
 * - Session termination occurs automatically after cookie download
 * - No persistent storage of sensitive authentication data
 */

import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  // ==========================================================================
  // STATE MANAGEMENT
  // ==========================================================================

  // Session Management State
  // Unique identifier for the current VM session
  const [sessionId, setSessionId] = useState(null);
  // IP address of the allocated VM instance
  const [vmIP, setVmIP] = useState(null);
  // Remote desktop access URL for iframe embedding
  const [url, setUrl] = useState(null);
  
  // UI State Management
  // Controls loading indicators and button states
  const [loading, setLoading] = useState(false);
  // Dynamic loading text that changes based on operation duration
  const [loadingText, setLoadingText] = useState('Starting up VM...');
  
  // Cookie Extraction State
  // Target domain for cookie extraction (e.g., 'reddit.com')
  const [targetDomain, setTargetDomain] = useState('');
  // Extracted cookies data from the remote browser
  const [cookies, setCookies] = useState(null);
  // Access token for secure cookie extraction operations
  const [accessToken, setAccessToken] = useState(null);
  
  // Historical Session State
  // For retrieving cookies from previously completed sessions
  const [pastSessionId, setPastSessionId] = useState('');
  const [pastAccessToken, setPastAccessToken] = useState('');

  // ==========================================================================
  // SIDE EFFECTS AND LIFECYCLE
  // ==========================================================================

  /**
   * Dynamic Loading Text Management
   * 
   * Provides progressive feedback during VM startup process.
   * Changes loading message after 60 seconds to indicate extended setup time.
   * This helps manage user expectations during potentially long VM initialization.
   * 
   * Dependencies:
   * - loading: Whether any operation is in progress
   * - vmIP: Whether VM has been allocated (null = still starting)
   */
  useEffect(() => {
    // Only show progressive loading text during VM startup
    if (loading && !vmIP) {
      // Initial loading message
      setLoadingText('Starting up VM...');

      // Update message after 60 seconds to indicate extended setup
      const timer = setTimeout(() => {
        setLoadingText('Finalizing setup on the VM...');
      }, 60000); /* 60 seconds*/

      // Cleanup timer on component unmount or dependency change
      return () => clearTimeout(timer);
    }
  }, [loading, vmIP]);


  // ==========================================================================
  // SESSION MANAGEMENT FUNCTIONS
  // ==========================================================================

  /**
   * Initialize Remote VM Session
   * 
   * Creates a new cloud VM instance with remote desktop access.
   * This function handles the complete session startup workflow:
   * 1. Sends session creation request to backend
   * 2. Receives VM allocation details (IP, session ID, access URL)
   * 3. Updates UI state to enable remote desktop access
   * 4. Handles errors gracefully with user feedback
   * 
   * Backend Response Expected:
   * - session_id: Unique identifier for tracking this VM session
   * - ip: IP address of the allocated VM instance
   * - url: Remote desktop access URL for iframe embedding
   * 
   * Error Handling:
   * - Network failures during VM allocation
   * - Backend service unavailability
   * - VM resource allocation failures
   */

  const startSession = async () => {
    // Set loading state to disable UI interactions
    setLoading(true);
    try {
      // Request new VM session from backend service
      const res = await axios.post('https://remote-login.onrender.com/session');
      
      // Store session details for subsequent operations
      setSessionId(res.data.session_id);
      setVmIP(res.data.ip);
      setUrl(res.data.url);
    } catch (error) {
      // Log technical details for debugging
      console.error('Failed to start session:', error);
      // Provide user-friendly error message
      alert('Error starting session.');
    } finally {
      // Reset loading state regardless of success or failure
      setLoading(false);
    }
  };

  /**
   * Terminate Remote VM Session
   * 
   * Properly shuts down the VM instance and cleans up resources.
   * This function ensures clean session termination:
   * 1. Validates that a session exists before attempting termination
   * 2. Sends deletion request to backend with session ID
   * 3. Cleans up all local state related to the session
   * 4. Resets UI to initial state for potential new sessions
   * 
   * Important: This function deallocates cloud resources and should
   * always be called when the session is no longer needed to prevent
   * unnecessary resource usage and associated costs.
   * 
   * Error Handling:
   * - Session already terminated on backend
   * - Network failures during termination request
   * - Backend service unavailability
   */

  const stopSession = async () => {
    // Prevent termination if no active session exists
    if (!sessionId) return;

    // Set loading state during termination process
    setLoading(true);
    try {
      // Send session termination request to backend
      await axios.delete(`https://remote-login.onrender.com/session/${sessionId}`);

      // Clean up all session-related state
      setSessionId(null);
      setVmIP(null);
      setUrl(null);
      setCookies(null);
    } catch (error) {
      // Log technical details for debugging
      console.error('Failed to stop session:', error);
      alert('Error stopping session.');
    } finally {
      // Reset loading state regardless of success or failure
      setLoading(false);
    }
  };

  // ==========================================================================
  // COOKIE EXTRACTION FUNCTIONS
  // ==========================================================================

  /**
   * Extract Cookies from Remote Browser
   * 
   * Performs domain-specific cookie extraction from the remote VM's browser.
   * This function orchestrates the complete cookie extraction workflow:
   * 1. Validates that VM session is active and domain is specified
   * 2. Sends extraction request with VM IP and target domain
   * 3. Receives extracted cookies and access token from backend
   * 4. Updates UI state to enable cookie download functionality
   * 
   * Backend Communication:
   * - Sends VM IP and target domain as query parameters
   * - Receives cookies array and access token for secure operations
   * 
   * Security Notes:
   * - Cookies are extracted in isolated VM environment
   * - Access token provides additional security for cookie operations
   * - No cookies are stored persistently in the frontend application
   * 
   * Error Handling:
   * - VM session not active or IP unavailable
   * - Invalid or inaccessible target domain
   * - Network failures during extraction request
   * - Browser automation failures on remote VM
   */
  const extractCookies = async () => {
    // Validate VM session is active
    if (!vmIP) return alert('Start session.')
    // Validate target domain is specified
    if (!targetDomain) return alert('Enter domain targer.');
    
    try {
      // Request cookie extraction from backend
      const res = await axios.get(`https://remote-login.onrender.com/extract_cookies`, {
        params: { ip: vmIP, domain: targetDomain }
      });
      // Store extracted data for download preparation
      setCookies(res.data.cookies);
      setAccessToken(res.data.access_token)
    } catch (error) {
      // Log technical details for debugging
      console.error('Failed to extract cookies:', error);
      alert('Error extracting cookies.');
    }
  };

  /**
   * Download Cookie Data as JSON File
   * 
   * Creates and downloads a JSON file containing session credentials and cookies.
   * This function handles the complete download and cleanup workflow:
   * 1. Prepares comprehensive data package with session info and cookies
   * 2. Creates downloadable blob with properly formatted JSON
   * 3. Triggers automatic file download via programmatic link interaction
   * 4. Performs appropriate cleanup based on session type (active vs historical)
   * 
   * Downloaded File Structure:
   * {
   *   "session_id": "uuid-string",
   *   "access_token": "secure-token-string", 
   *   "cookies": [array-of-cookie-objects]
   * }
   * 
   * Cleanup Behavior:
   * - Active sessions: Terminates VM session and resets domain input
   * - Historical sessions: Clears cookie data and credential inputs
   * 
   * Security Considerations:
   * - Automatic session termination prevents resource leakage
   * - Local state cleanup prevents data persistence
   * - JSON file contains all necessary data for external authentication
   */
  const downloadCookies = () => {
    // Prepare comprehensive data package for download
    const fileData = {
      session_id: sessionId || pastSessionId,
      access_token: accessToken || pastAccessToken,
      cookies: cookies
    };

    // Create downloadable JSON blob with proper formatting
    const blob = new Blob([JSON.stringify(fileData, null, 2)], {
      type: 'application/json'
    });

    // Generate temporary download URL
    const url = URL.createObjectURL(blob);

    // Create and trigger download via programmatic link interaction
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cookies.json';
    a.click();

    // Perform cleanup based on session type
    if (sessionId && vmIP) {
      // Active session: terminate VM and reset domain input
      stopSession();
      setTargetDomain('');
    } else {
      // Historical session: clear cookie data and credential inputs
      setCookies(null);
      setPastSessionId('');
      setPastAccessToken('');
    }
  };

  // ==========================================================================
  // HISTORICAL DATA RETRIEVAL FUNCTIONS
  // ==========================================================================

  /**
   * Retrieve Cookies from Past Session
   * 
   * Fetches previously extracted cookies using historical session credentials.
   * This function enables users to retrieve cookie data from completed sessions:
   * 1. Validates that both session ID and access token are provided
   * 2. Sends authenticated request to backend with historical credentials
   * 3. Receives and stores cookie data for download preparation
   * 4. Handles authentication failures and invalid credential scenarios
   * 
   * Use Cases:
   * - Retrieving cookies after accidental browser closure
   * - Accessing cookies from sessions completed on different devices
   * - Batch processing of multiple historical cookie sets
   * 
   * Security Notes:
   * - Requires both session ID and access token for authentication
   * - Backend validates credentials before returning sensitive cookie data
   * - No modification of historical data is permitted
   * 
   * Error Handling:
   * - Missing or invalid session credentials
   * - Expired or already-consumed session tokens
   * - Network failures during retrieval request
   * - Backend authentication failures
   */
  const fetchPastCookies = async () => {
    // Validate that both credentials are provided
    if (!pastSessionId || !pastAccessToken) return alert("Enter session ID and access token.");
    
    try {
      // Request historical cookie data with authentication
      const res = await axios.get('https://remote-login.onrender.com/cookies', {
        params: {
          session_id: pastSessionId,
          access_token: pastAccessToken
        }
      });

      // Store retrieved cookie data for download
      setCookies(res.data.cookies);
    } catch (error) {
      // Log technical details for debugging
      console.error('Failed to load past cookies:', error);
      alert("Could not load cookies. Check session ID and token.");
    }
  };

  // ==========================================================================
  // RENDER COMPONENT UI
  // ==========================================================================

  return (
    <div className="container">
      {/* Application Header */}
      <h1>Remote-Login</h1>

      {/* ================================================================ */}
      {/* SESSION CONTROL BUTTONS                                          */}
      {/* ================================================================ */}
      <div className="buttons">
        {/* Start Session Button */}
        <button onClick={startSession} disabled={loading || sessionId}>   {/* Disabled during loading or if session exists */}
          <span className="shadow"></span>
          <span className="edge"></span>
          <span className="front text">Start Session</span>
        </button>

        {/* Stop Session Button */}
        <button onClick={stopSession} disabled={loading || !sessionId}>   {/* // Disabled during loading or if no session */}
          <span className="shadow"></span>
          <span className="edge"></span>
          <span className="front text">Stop Session</span>
        </button>
      </div>

      {/* ================================================================ */}
      {/* LOADING INDICATOR                                                */}
      {/* ================================================================ */}
      {/* Display loading animation and progressive text during VM startup */}
      { loading && !vmIP && (
        <div className="loading">
          {/* Animated SVG loading spinner */}
          <svg viewBox="25 25 50 50">
            <circle r="20" cy="50" cx="50"></circle>
          </svg>
          {/* Dynamic loading text that updates based on elapsed time */}
          <span className="loading-text">{loadingText}</span>
        </div>
      )}

      {/* ================================================================ */}
      {/* ACTIVE SESSION INTERFACE                                         */}
      {/* ================================================================ */}
      {/* Display when VM is active and ready for cookie extraction */}
      { vmIP &&(
        <>
          {/* Cookie Extraction Form */}
          <div className="cookie-form-container">
            <div className="cookie-form">
              {/* Domain Input Field */}
              <div className="coolinput">
                <label for="input" className="text">Domain:</label>
                <input 
                  type="text"
                  value={targetDomain}
                  onChange={(e) => setTargetDomain(e.target.value)}
                  placeholder="e.g. reddit.com" 
                  name="input" 
                  className="input"
                  autoComplete="off"      // Prevent browser autocomplete interference
                />
              </div>

              {/* Extract Cookies Button */}
              <button onClick={extractCookies}>
                <span className="shadow"></span>
                <span className="edge"></span>
                <span className="front text">Extract Cookies</span>
              </button>

              {/* Cookie Download Section */}
              {/* Display after successful cookie extraction */}
              { cookies && accessToken &&(
                <>
                  {/* Session Information Display */}
                  <div className="session-info">
                    <p><strong>Session ID:</strong> {sessionId}</p>
                    <p><strong>Access Token:</strong> {accessToken}</p>
                  </div>

                  {/* Download Cookies Button */}
                  <button onClick={downloadCookies}>
                    <span className="shadow"></span>
                    <span className="edge"></span>
                    <span className="front text">Download Cookies</span>
                  </button>

                  {/* User Warning */}
                  <div className="warning-text">
                    Warning: The session will be terminated after downloading cookies.
                  </div>
                </>
              )}
            </div>
          </div>
          
          {/* ============================================================ */}
          {/* REMOTE DESKTOP IFRAME                                        */}
          {/* ============================================================ */}
          {/* Embedded remote desktop interface for manual browser interaction */}
          <div className="iframe-container">
            <iframe
              src={`${url}`}
              title="Remote Desktop"
              width="78%"
              height="730"
            />
          </div>
        </>
      )}

      {/* ================================================================ */}
      {/* HISTORICAL COOKIE RETRIEVAL INTERFACE                           */}
      {/* ================================================================ */}
      {/* Display when no active session exists for retrieving past cookies */}
      { !loading && !sessionId && !vmIP && (
        <div className="past-cookie-form-container">
          <div className="past-cookie-form">
            <h3>Retrieve Past Cookies</h3>

            {/* Session ID Input */}
            <div className="coolinput">
              <label for="input" className="text">Session ID:</label>
              <input 
                type="text"
                value={pastSessionId}
                onChange={(e) => setPastSessionId(e.target.value)} 
                name="input" 
                className="input"
                autoComplete="off"        // Prevent browser autocomplete interference
              />
            </div>

            {/* Access Token Input */}
            <div className="coolinput">
              <label for="input" className="text">Access Token:</label>
              <input 
                type="text"
                value={pastAccessToken}
                onChange={(e) => setPastAccessToken(e.target.value)} 
                name="input" 
                className="input"
                autoComplete="off"        // Prevent browser autocomplete interference
              />
            </div>

            {/* Fetch Past Cookies Button */}
            <button onClick={fetchPastCookies}>
              <span className="shadow"></span>
              <span className="edge"></span>
              <span className="front text">Fetch Cookies</span>
            </button>

            {/* Historical Cookie Download Section */}
            {/* Display after successful historical cookie retrieval */}
            {cookies && !sessionId && (
              <div className="download-past">
                <p>Cookies Fetched Successfully</p>
                <button onClick={downloadCookies}>
                  <span className="shadow"></span>
                  <span className="edge"></span>
                  <span className="front text">Download Past Cookies</span>
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
