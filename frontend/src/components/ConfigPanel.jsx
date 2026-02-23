import React, { useState } from 'react';

export default function ConfigPanel({ onStart, disabled }) {
  const [task, setTask] = useState("");
  const [model, setModel] = useState("gpt-4");
  const [autoApply, setAutoApply] = useState(false);
  const [openRouterKey, setOpenRouterKey] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    onStart({ task, model, auto_apply: autoApply, openrouter_api_key: openRouterKey });
  };

  return (
    <div className="panel">
      <h2>Configuration</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Task Description</label>
          <textarea
            className="form-control"
            rows={4}
            value={task}
            onChange={(e) => setTask(e.target.value)}
            required
            disabled={disabled}
            placeholder="Describe the task for the agents..."
          />
        </div>

        <div className="form-group">
          <label>Model</label>
          <select
            className="form-control"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={disabled}
          >
            <option value="gpt-4">GPT-4</option>
            <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
            <option value="anthropic/claude-3-opus">Claude 3 Opus</option>
          </select>
        </div>

        <div className="form-group">
            <label>OpenRouter API Key (Optional)</label>
            <input
                type="password"
                className="form-control"
                value={openRouterKey}
                onChange={(e) => setOpenRouterKey(e.target.value)}
                placeholder="sk-or-..."
                disabled={disabled}
            />
        </div>

        <div className="form-group">
          <label style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
            <input
              type="checkbox"
              checked={autoApply}
              onChange={(e) => setAutoApply(e.target.checked)}
              disabled={disabled}
            />
            Auto-apply Verifier Suggestions
          </label>
        </div>

        <button type="submit" className="btn" disabled={disabled || !task.trim()}>
          {disabled ? "Running..." : "Start Task"}
        </button>
      </form>
    </div>
  );
}
