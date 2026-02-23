import React, { useEffect, useRef } from 'react';

export default function Chat({ messages }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="chat-container">
      {messages.length === 0 && (
        <div style={{color: 'gray', textAlign: 'center'}}>
          No messages yet. Start a task to begin.
        </div>
      )}

      {messages.map((msg, idx) => (
        <div key={idx} className={`message ${msg.sender === 'User' ? 'user' : ''}`}>
          <div className="message-meta">
            <span>{msg.sender} → {msg.recipient}</span>
            <span>{new Date(msg.ts * 1000).toLocaleTimeString()}</span>
          </div>
          <div style={{whiteSpace: 'pre-wrap'}}>{msg.content}</div>

          {/* Verifier Result Display */}
          {msg.verifier && (
            <div className={`verifier-result ${msg.verifier.verdict === 'pass' ? 'verifier-pass' : 'verifier-fail'}`}>
              <strong>Verifier: {msg.verifier.verdict.toUpperCase()} ({msg.verifier.confidence})</strong>
              <div>{msg.verifier.reason}</div>
              {msg.verifier.suggested_actions?.length > 0 && (
                <ul style={{margin: '0.5rem 0 0 1rem', padding: 0}}>
                  {msg.verifier.suggested_actions.map((act, i) => (
                    <li key={i}>{act}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
