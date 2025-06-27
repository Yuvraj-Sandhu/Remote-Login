import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [sessionId, setSessionId] = useState(null);
  const [vmIP, setVmIP] = useState(null);
  const [loading, setLoading] = useState(false);
  const [targetDomain, setTargetDomain] = useState('');
  const [cookies, setCookies] = useState(null);
  const [loadingText, setLoadingText] = useState('Starting up VM...');
  const [accessToken, setAccessToken] = useState(null);
  const [pastSessionId, setPastSessionId] = useState('');
  const [pastAccessToken, setPastAccessToken] = useState('');


  useEffect(() => {
    if (loading && !vmIP) {
      setLoadingText('Starting up VM...');
      const timer = setTimeout(() => {
        setLoadingText('Finalizing setup on the VM...');
      }, 60000); /* 60 seconds*/
      return () => clearTimeout(timer);
    }
  }, [loading, vmIP]);

  const startSession = async () => {
    setLoading(true);
    try {
      const res = await axios.post('https://remote-login.onrender.com/session');
      setSessionId(res.data.session_id);
      setVmIP(res.data.ip);
    } catch (error) {
      console.error('Failed to start session:', error);
      alert('Error starting session.');
    } finally {
      setLoading(false);
    }
  };

  const stopSession = async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      await axios.delete(`https://remote-login.onrender.com/session/${sessionId}`);
      setSessionId(null);
      setVmIP(null);
      setCookies(null);
    } catch (error) {
      console.error('Failed to stop session:', error);
      alert('Error stopping session.');
    } finally {
      setLoading(false);
    }
  };

  const extractCookies = async () => {
    if (!vmIP) return alert('Start session.')
    if (!targetDomain) return alert('Enter domain targer.');
    try {
      const res = await axios.get(`https://remote-login.onrender.com/extract_cookies`, {
        params: { ip: vmIP, domain: targetDomain }
      });
      setCookies(res.data.cookies);
      setAccessToken(res.data.access_token)
    } catch (error) {
      console.error('Failed to extract cookies:', error);
      alert('Error extracting cookies.');
    }
  };

  const downloadCookies = () => {
    const fileData = {
      session_id: sessionId || pastSessionId,
      access_token: accessToken || pastAccessToken,
      cookies: cookies
    };
    const blob = new Blob([JSON.stringify(fileData, null, 2)], {
      type: 'application/json'
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cookies.json';
    a.click();
    if (sessionId && vmIP) {
      stopSession();
      setTargetDomain('');
    } else {
      setCookies(null);
      setPastSessionId('');
      setPastAccessToken('');
    }
  };

  const fetchPastCookies = async () => {
    if (!pastSessionId || !pastAccessToken) return alert("Enter session ID and access token.");
    try {
      const res = await axios.get('https://remote-login.onrender.com/cookies', {
        params: {
          session_id: pastSessionId,
          access_token: pastAccessToken
        }
      });
      setCookies(res.data.cookies);
    } catch (error) {
      console.error('Failed to load past cookies:', error);
      alert("Could not load cookies. Check session ID and token.");
    }
  };

  return (
    <div className="container">
      <h1>Remote-Login</h1>
      <div className="buttons">
        <button onClick={startSession} disabled={loading || sessionId}>
          <span className="shadow"></span>
          <span className="edge"></span>
          <span className="front text">Start Session</span>
        </button>
        <button onClick={stopSession} disabled={loading || !sessionId}>
          <span className="shadow"></span>
          <span className="edge"></span>
          <span className="front text">Stop Session</span>
        </button>
      </div>
      { loading && !vmIP && (
        <div className="loading">
          <svg viewBox="25 25 50 50">
            <circle r="20" cy="50" cx="50"></circle>
          </svg>
          <span className="loading-text">{loadingText}</span>
        </div>
      )}
      { vmIP &&(
        <>
          <div className="cookie-form-container">
            <div className="cookie-form">
              <div className="coolinput">
                <label for="input" className="text">Domain:</label>
                <input 
                  type="text"
                  value={targetDomain}
                  onChange={(e) => setTargetDomain(e.target.value)}
                  placeholder="e.g. reddit.com" 
                  name="input" 
                  className="input"
                  autoComplete="off"
                />
              </div>
              <button onClick={extractCookies}>
                <span className="shadow"></span>
                <span className="edge"></span>
                <span className="front text">Extract Cookies</span>
              </button>
              { cookies && accessToken &&(
                <>
                  <div className="session-info">
                    <p><strong>Session ID:</strong> {sessionId}</p>
                    <p><strong>Access Token:</strong> {accessToken}</p>
                  </div>
                  <button onClick={downloadCookies}>
                    <span className="shadow"></span>
                    <span className="edge"></span>
                    <span className="front text">Download Cookies</span>
                  </button>
                  <div className="warning-text">
                    Warning: The session will be terminated after downloading cookies.
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="iframe-container">
            <iframe
              src={`https://${vmIP}:443/vnc.html`}
              title="Remote Desktop"
              width="78%"
              height="730"
            />
          </div>
        </>
      )}
      { !loading && !sessionId && !vmIP && (
        <div className="past-cookie-form-container">
          <div className="past-cookie-form">
            <h3>Retrieve Past Cookies</h3>
            <div className="coolinput">
              <label for="input" className="text">Session ID:</label>
              <input 
                type="text"
                value={pastSessionId}
                onChange={(e) => setPastSessionId(e.target.value)} 
                name="input" 
                className="input"
                autoComplete="off"
              />
            </div>
            <div className="coolinput">
              <label for="input" className="text">Access Token:</label>
              <input 
                type="text"
                value={pastAccessToken}
                onChange={(e) => setPastAccessToken(e.target.value)} 
                name="input" 
                className="input"
                autoComplete="off"
              />
            </div>
            <button onClick={fetchPastCookies}>
              <span className="shadow"></span>
              <span className="edge"></span>
              <span className="front text">Fetch Cookies</span>
            </button>

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
