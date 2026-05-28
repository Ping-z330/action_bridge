# ActionBridge

ActionBridge is a meeting-to-execution agent MVP that turns meeting notes into structured action items and sends the result into team collaboration workflows.

## What It Does

This project focuses on a lightweight but practical meeting workflow:

1. Submit a meeting title and transcript from the web UI.
2. Parse the transcript into:
   - summary
   - decisions
   - action items
3. Store the parsed result in the backend database.
4. Display the meeting result on a dashboard.
5. Send the meeting summary and action items to a Feishu group webhook as Feishu cards.
6. Send follow-up reminders for unfinished action items.

## Current MVP Scope

The current version already includes:

- FastAPI backend for meeting creation, querying, action item updates, and Feishu delivery
- Next.js frontend for transcript submission and meeting detail viewing
- DeepSeek-based transcript parsing
- OpenAI-compatible parser fallback path
- Rule-based fallback when LLM parsing is unavailable or too generic
- SQLite persistence for meetings, action items, and task records
- Editable action items for owner, deadline, and status
- Feishu webhook integration with interactive card delivery
- Manual follow-up reminder flow for unfinished action items
- Automated backend tests

## Tech Stack

### Backend

- Python
- FastAPI
- SQLAlchemy
- SQLite
- OpenAI Python SDK
- httpx
- python-dotenv
- pytest

### Frontend

- Next.js
- React
- TypeScript

## Project Structure

```text
ActionBridge/
  backend/
    app/
      api/
      core/
      db/
      models/
      schemas/
      services/
    tests/
  frontend/
    app/
    components/
    lib/
  docs/
```

## Environment Setup

Create a local `.env` file in the project root. You can copy `.env.example` and fill in your real values.

Example:

```env
DEEPSEEK_API_KEY=your_real_deepseek_key
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
ACTIONBRIDGE_PARSER_PROVIDER=deepseek

FEISHU_WEBHOOK_URL=your_real_feishu_webhook
```

## Run the Backend

From the `backend` directory:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The backend will start at:

```text
http://localhost:8000
```

Swagger docs:

```text
http://localhost:8000/docs
```

## Run the Frontend

From the `frontend` directory:

```bash
npm install
npm run dev
```

The frontend will start at:

```text
http://localhost:3000
```

## Testing

Run backend tests from the `backend` directory:

```bash
pytest -q
```

## Example Workflow

1. Open the frontend dashboard.
2. Paste a meeting transcript.
3. Create the meeting.
4. Review the extracted summary, decisions, and action items.
5. Update action item owner, deadline, or status from the detail page.
6. Click `发送到飞书` to push the meeting summary card into a Feishu group.
7. Click `发送跟进提醒` to push a follow-up card for unfinished action items.

## Notes on Parsing

The parser currently supports:

- DeepSeek as the default provider
- OpenAI as an alternative provider
- Rule-based fallback when:
  - no valid API key is configured
  - the provider call fails
  - the LLM response is too generic to be useful

This makes the MVP more stable during demos and local development.

## Roadmap

Planned next steps include:

- richer Feishu card interactions
- meeting-to-task execution tracking
- parser mode visibility in the UI
- stronger long-term memory and workflow orchestration

## Why This Project

ActionBridge is designed as a practical B-end productivity tool rather than a pure AI demo. The goal is to reduce manual work after meetings by moving teams faster from discussion to execution.
