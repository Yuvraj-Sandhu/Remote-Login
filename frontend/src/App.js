import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [sessionId, setSessionId] = useState(null);
  const [vmIP, setVmIP] = useState(null);
  const [loading, setLoading] = useState(false);

  const startSession = async () => {
    setLoading(true);
    try {
      const res = await axios.post('http://localhost:8000/session');
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
      await axios.delete(`http://localhost:8000/session/${sessionId}`);
      setSessionId(null);
      setVmIP(null);
    } catch (error) {
      console.error('Failed to stop session:', error);
      alert('Error stopping session.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <h1>Remote-Login</h1>
      <div className="buttons">
        <button onClick={startSession} disabled={loading || sessionId}>
          Start Session
        </button>
        <button onClick={stopSession} disabled={loading || !sessionId}>
          Stop Session
        </button>
      </div>
      {vmIP && (
        <div className="iframe-container">
          <iframe
            src={`http://${vmIP}:6080/vnc.html`}
            title="Remote Desktop"
            width="150%"
            height="750"
          />
        </div>
      )}
    </div>
  );
}

export default App;
