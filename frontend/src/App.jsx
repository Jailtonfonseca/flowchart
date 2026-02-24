import React, { useMemo, useState } from 'react'
import ConfigPanel from './components/ConfigPanel'
import Settings from './components/Settings'
import Chat from './components/Chat'
import CredentialModal from './components/CredentialModal'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function App() {
  const [config, setConfig] = useState({
    task: '',
    model: 'openai/gpt-4o-mini',
    max_agents: 3,
    auto_apply: true,
    user_id: 'user123',
    openrouter_api_key: '',
  })
  const [events, setEvents] = useState([])
  const [taskId, setTaskId] = useState(null)
  const [running, setRunning] = useState(false)
  const [credentials, setCredentials] = useState({})
  const [modalOpen, setModalOpen] = useState(false)
  const [modalRequest, setModalRequest] = useState(null)
  const [modalValue, setModalValue] = useState('')

  const pending = useMemo(
    () => Object.values(credentials).filter((v) => v.pending),
    [credentials],
  )

  const connectWs = (id) => {
    const wsUrl = API_BASE.replace('http', 'ws') + `/ws/${id}`
    const ws = new WebSocket(wsUrl)
    ws.onmessage = (msg) => {
      const evt = JSON.parse(msg.data)
      setEvents((old) => [...old, evt])
      if (evt.kind === 'credential_request') {
        const req = evt.payload
        setCredentials((old) => ({
          ...old,
          [req.provider]: {
            ...(old[req.provider] || {}),
            description: req.description,
            pending: true,
          },
        }))
        setModalRequest(req)
        setModalOpen(true)
      }
      if (evt.kind === 'finished') {
        setRunning(false)
      }
      if (evt.kind === 'action_result' && evt.payload.action === 'request_credential') {
        const provider = evt.payload.detail.split('for ')[1]
        if (provider) {
          setCredentials((old) => ({
            ...old,
            [provider]: { ...(old[provider] || {}), pending: false },
          }))
        }
      }
    }
    ws.onclose = () => setRunning(false)
  }

  const startTask = async () => {
    setEvents([])
    const res = await fetch(`${API_BASE}/start-task`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    })
    const data = await res.json()
    setTaskId(data.task_id)
    setRunning(true)
    connectWs(data.task_id)
  }

  const handleSave = async (provider, value, submit) => {
    setCredentials((old) => ({
      ...old,
      [provider]: { ...(old[provider] || {}), value },
    }))
    if (!submit || !value) return
    await fetch(`${API_BASE}/credentials`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: config.user_id, provider, value }),
    })
    setCredentials((old) => ({
      ...old,
      [provider]: { ...(old[provider] || {}), pending: false },
    }))
    setModalOpen(false)
    setModalRequest(null)
    setModalValue('')
  }

  return (
    <main>
      <h1>Multi-Agent Orchestrator</h1>
      {taskId && <p>Task ID: {taskId}</p>}
      <div className="grid">
        <ConfigPanel config={config} onChange={setConfig} onStart={startTask} running={running} />
        <Settings userId={config.user_id} credentials={credentials} pending={pending} onSave={handleSave} />
      </div>
      <Chat events={events} />
      <CredentialModal
        open={modalOpen}
        request={modalRequest}
        value={modalValue}
        setValue={setModalValue}
        onClose={() => setModalOpen(false)}
        onSubmit={() => modalRequest && handleSave(modalRequest.provider, modalValue, true)}
      />
    </main>
  )
}
