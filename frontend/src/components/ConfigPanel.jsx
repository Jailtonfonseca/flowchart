import React from 'react'

export default function ConfigPanel({ config, onChange, onStart, running }) {
  return (
    <section className="panel">
      <h2>Configuração</h2>
      <label>Tarefa
        <textarea value={config.task} onChange={(e) => onChange({ ...config, task: e.target.value })} />
      </label>
      <label>Modelo
        <input value={config.model} onChange={(e) => onChange({ ...config, model: e.target.value })} />
      </label>
      <label>User ID
        <input value={config.user_id} onChange={(e) => onChange({ ...config, user_id: e.target.value })} />
      </label>
      <label>Max agents
        <input type="number" value={config.max_agents} onChange={(e) => onChange({ ...config, max_agents: Number(e.target.value) })} />
      </label>
      <label className="row">
        <input type="checkbox" checked={config.auto_apply} onChange={(e) => onChange({ ...config, auto_apply: e.target.checked })} />
        Auto apply
      </label>
      <button disabled={running || !config.task.trim()} onClick={onStart}>Start task</button>
    </section>
  )
}
