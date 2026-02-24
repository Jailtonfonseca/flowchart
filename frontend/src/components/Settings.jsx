import React from 'react'

export default function Settings({ userId, credentials, pending, onSave }) {
  return (
    <section className="panel">
      <h2>Settings / Credenciais</h2>
      {pending.length > 0 && (
        <div className="banner">
          Execução pausada aguardando credencial: {pending.map((p) => p.provider).join(', ')}
        </div>
      )}
      {Object.entries(credentials).map(([provider, meta]) => (
        <div key={provider} className={`credential-card ${meta.pending ? 'pending' : ''}`}>
          <h3>{provider}</h3>
          <p>{meta.description || 'Sem descrição'}</p>
          <input
            type="password"
            placeholder={`Insira ${provider} key`}
            value={meta.value || ''}
            onChange={(e) => onSave(provider, e.target.value, false)}
          />
          <button onClick={() => onSave(provider, meta.value || '', true)}>Salvar e continuar</button>
        </div>
      ))}
      <small>As chaves são enviadas para o backend. Evite armazenar no browser.</small>
      <div>User: {userId}</div>
    </section>
  )
}
