import React from 'react'

export default function Chat({ events }) {
  return (
    <section className="panel">
      <h2>Chat / Audit Trail</h2>
      <div className="log">
        {events.map((evt, idx) => (
          <pre key={`${evt.kind}-${idx}`}>{JSON.stringify(evt, null, 2)}</pre>
        ))}
      </div>
    </section>
  )
}
