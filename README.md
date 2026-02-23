# AutoGen Agent Builder + Verifier App

A Streamlit application that dynamically builds a team of AI agents using AutoGen to solve a user task. It features a real-time **Verifier** agent that audits every message, provides a pass/fail verdict, and can automatically suggest or apply corrective actions (like adding/removing agents).

## Features

- **Dynamic Team Building**: Uses AutoGen's `AgentBuilder` to create agents based on the task description.
- **Real-time Verification**: A dedicated Verifier agent checks every message against the task context.
- **Auto-Correction**: If enabled, the Verifier can modify the team structure or inject instructions to fix issues.
- **Streamlit UI**: Visualize the chat and audit trail in real-time.
- **Dockerized**: Easy deployment with Docker Compose.

## Prerequisites

- Python 3.11+
- [OpenRouter](https://openrouter.ai/) API Key (or OpenAI compatible key).

## Setup

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd <repo-dir>
   ```

2. **Configure Environment**:
   Copy `.env.example` to `.env` and fill in your API key.
   ```bash
   cp .env.example .env
   # Edit .env
   ```

## Running with Docker (Recommended)

1. Build and run:
   ```bash
   docker compose up --build -d
   ```
2. Access the app at `http://localhost:8501`.
3. Stop:
   ```bash
   docker compose down
   ```

## Running Locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run Streamlit:
   ```bash
   streamlit run app.py
   ```

## Testing

Run unit tests:
```bash
pytest
```

Run smoke test (requires Docker):
```bash
./scripts/smoke_run.sh
```

## Architecture

- **`app.py`**: Main application logic. Handles Streamlit UI and spawns a background thread for the AutoGen orchestration.
- **`Verifier`**: A class that calls the LLM to verify messages and returns structured JSON verdicts.
- **`AgentBuilder`**: Uses `pyautogen` to generate agent configurations.

## Troubleshooting

- **Import Errors**: Ensure you have `pyautogen` installed. `pip install pyautogen`.
- **Verifier Failures**: Check your OpenRouter API key and credit balance. The app will fallback to "pass" if the verifier is unavailable.
