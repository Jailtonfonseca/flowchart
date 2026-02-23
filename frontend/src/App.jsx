import React, { useState, useEffect, useRef } from 'react';
import ConfigPanel from './components/ConfigPanel';
import Chat from './components/Chat';
import Settings from './components/Settings';
import CredentialModal from './components/CredentialModal';

const API_BASE = "http://localhost:8000";

function App() {
  const [taskId, setTaskId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState("idle");
  const [credentialRequests, setCredentialRequests] = useState([]);
  const [showModal, setShowModal] = useState(null);
  const [userId, setUserId] = useState("user123"); // Mock user ID
  const wsRef = useRef(null);

  const startTask = async (config) => {
    setStatus("running");
    setMessages([]);
    setCredentialRequests([]);

    try {
      const res = await fetch(`${API_BASE}/start-task`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...config, user_id: userId })
      });
      const data = await res.json();
      setTaskId(data.task_id);
      connectWebSocket(data.task_id);
    } catch (e) {
      console.error(e);
      setStatus("error");
      setMessages(prev => [...prev, { sender: "System", content: `Error: ${e.message}`, ts: Date.now()/1000 }]);
    }
  };

  const connectWebSocket = (tid) => {
    if (wsRef.current) wsRef.current.close();

    const ws = new WebSocket(`ws://localhost:8000/ws/${tid}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      handleEvent(data);
    };

    ws.onclose = () => {
      console.log("WS closed");
      if (status === 'running') setStatus("finished");
    };
  };

  const handleEvent = (event) => {
    const { kind, payload } = event;

    if (kind === 'agent_message') {
      setMessages(prev => [...prev, payload]);
    } else if (kind === 'verifier_result') {
      setMessages(prev => {
        const copy = [...prev];
        // Attach to last message if it exists
        if (copy.length > 0) {
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { ...last, verifier: payload };
        }
        return copy;
      });
    } else if (kind === 'credential_request') {
      setCredentialRequests(prev => [...prev, payload]);
      // Show modal for immediate action
      setShowModal(payload);
    } else if (kind === 'info' || kind === 'error' || kind === 'finished') {
        setMessages(prev => [...prev, {
            sender: "System",
            content: payload.msg,
            ts: payload.ts,
            type: kind
        }]);
        if (kind === 'finished') setStatus("finished");
    } else if (kind === 'action_result') {
        setMessages(prev => [...prev, {
            sender: "Runner",
            content: `Action: ${payload.action} - ${payload.detail}`,
            ts: payload.ts,
            type: 'action'
        }]);
    }
  };

  const handleSaveCredential = async (provider, value) => {
    try {
      await fetch(`${API_BASE}/credentials`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, provider, value })
      });

      // Remove from pending
      setCredentialRequests(prev => prev.filter(r => r.provider !== provider));
      setShowModal(null);

      // Notify WS (optional, backend handles it via Event, but we can send explicit ack)
      if (wsRef.current) {
        wsRef.current.send(JSON.stringify({ cmd: "credential_provided" }));
      }

    } catch (e) {
      console.error(e);
      alert("Failed to save credential");
    }
  };

  return (
    <div className="main-layout">
      <div className="sidebar">
        <div className="header">
           <strong>AutoGen Runner</strong>
        </div>
        <ConfigPanel onStart={startTask} disabled={status === 'running' || status === 'paused'} />
        <Settings
            userId={userId}
            credentialRequests={credentialRequests}
            onSaveCredential={handleSaveCredential}
        />
      </div>

      <div className="content">
        {credentialRequests.length > 0 && (
            <div className="banner">
                ⚠️ Credential Required: {credentialRequests[0].provider} - Execution Paused
                <button className="btn btn-secondary" onClick={() => setShowModal(credentialRequests[0])}>Enter Key</button>
            </div>
        )}

        <div className="header">
            <span>Task ID: {taskId || "Not started"}</span>
            <span>Status: {status}</span>
        </div>

        <Chat messages={messages} />
      </div>

      {showModal && (
        <CredentialModal
            request={showModal}
            onSave={handleSaveCredential}
            onCancel={() => setShowModal(null)}
        />
      )}
    </div>
  );
}

export default App;
