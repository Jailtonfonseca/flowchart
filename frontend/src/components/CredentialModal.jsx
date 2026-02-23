import React, { useState } from 'react';

export default function CredentialModal({ request, onSave, onCancel }) {
  const [value, setValue] = useState("");

  if (!request) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(request.provider, value);
    setValue("");
  };

  return (
    <div className="modal-overlay">
      <div className="modal">
        <h3>Credential Required: {request.provider}</h3>
        <p>{request.description}</p>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>{request.provider} API Key/Token</label>
            <input
              type="password"
              className="form-control"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoFocus
            />
          </div>
          <div style={{display: 'flex', gap: '1rem', justifyContent: 'flex-end'}}>
            <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
            <button type="submit" className="btn">Save & Resume</button>
          </div>
        </form>
      </div>
    </div>
  );
}
