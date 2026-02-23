import React, { useEffect, useState } from 'react';

export default function Settings({ userId, credentialRequests, onSaveCredential }) {
  const [providers, setProviders] = useState([]);
  const [newCreds, setNewCreds] = useState({});

  useEffect(() => {
    // Fetch known credentials
    if (!userId) return;
    fetch(`http://localhost:8000/credentials/${userId}`)
      .then(res => res.json())
      .then(setProviders)
      .catch(console.error);
  }, [userId]);

  const handleInputChange = (provider, value) => {
    setNewCreds(prev => ({ ...prev, [provider]: value }));
  };

  const handleSave = (provider) => {
    const value = newCreds[provider];
    if (value) {
      onSaveCredential(provider, value);
      setNewCreds(prev => ({ ...prev, [provider]: '' }));
      if (!providers.includes(provider)) {
        setProviders(prev => [...prev, provider]);
      }
    }
  };

  return (
    <div className="panel">
      <h2>Credentials</h2>

      {/* Pending Requests */}
      {credentialRequests.length > 0 && (
        <div className="verifier-result verifier-fail">
          <strong>Pending Requests:</strong>
          <ul>
            {credentialRequests.map(req => (
              <li key={req.request_id}>
                {req.provider}: {req.description}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* List of existing */}
      <div>
        <h3>Stored Providers</h3>
        <ul>
          {providers.map(p => <li key={p}>{p} (Stored)</li>)}
        </ul>
      </div>

      {/* Dynamic Input for pending */}
      {credentialRequests.map(req => (
        <div key={req.request_id} className="form-group" style={{border: '1px solid orange', padding: '1rem'}}>
          <label style={{color: 'orange'}}>REQUIRED: {req.provider.toUpperCase()}</label>
          <p className="message-meta">{req.description}</p>
          <input
            type="password"
            className="form-control"
            placeholder={`Enter ${req.provider} key`}
            value={newCreds[req.provider] || ''}
            onChange={(e) => handleInputChange(req.provider, e.target.value)}
          />
          <button className="btn" style={{marginTop: '0.5rem'}} onClick={() => handleSave(req.provider)}>
            Save & Continue
          </button>
        </div>
      ))}

      {/* Manual Add */}
      <div className="form-group">
        <label>Add New Credential</label>
        <div style={{display: 'flex', gap: '0.5rem'}}>
            <input
                placeholder="Provider (e.g. github)"
                className="form-control"
                id="new-provider-name"
            />
            <input
                type="password"
                placeholder="Value"
                className="form-control"
                id="new-provider-value"
            />
            <button className="btn" onClick={() => {
                const p = document.getElementById('new-provider-name').value;
                const v = document.getElementById('new-provider-value').value;
                if(p && v) handleSave(p);
                // hacky direct dom access for speed
                document.getElementById('new-provider-name').value = '';
                document.getElementById('new-provider-value').value = '';
            }}>Add</button>
        </div>
      </div>

    </div>
  );
}
