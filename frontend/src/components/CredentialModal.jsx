import React from 'react'

export default function CredentialModal({ open, request, value, setValue, onClose, onSubmit }) {
  if (!open || !request) return null
  return (
    <div className="modal-overlay">
      <div className="modal">
        <h3>Inserir credencial: {request.provider}</h3>
        <p>{request.description}</p>
        <input type="password" value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
        <div className="row">
          <button onClick={onClose}>Cancelar</button>
          <button onClick={onSubmit}>Salvar e continuar</button>
        </div>
      </div>
    </div>
  )
}
