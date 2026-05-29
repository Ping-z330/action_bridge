# ActionBridge

ActionBridge is a meeting-to-execution agent MVP that turns meeting transcripts into structured action items, pushes them into Feishu, and keeps unfinished work moving through follow-up reminders.

## What It Does

ActionBridge focuses on a practical meeting workflow:

1. Submit a meeting title and transcript from the web UI.
2. Parse the transcript into:
   - summary
   - decisions
   - action items
3. Split action item content from owner information when the transcript clearly starts with a role or assignee.
4. Store the parsed result in the backend database.
5. Review and edit action item owner, deadline, and status from the detail page.
6. Send meeting summaries and unfinished tasks to Feishu as interactive cards.
7. Run follow-up reminders manually or automatically on a schedule.

## Current MVP Scope

The current version already includes:

- FastAPI backend for meeting creation, querying, action item updates, and Feishu delivery
- Next.js frontend for transcript submission, meeting detail viewing, and follow-up triggering
- DeepSeek-based transcript parsing
- OpenAI-compatible parser path
- Rule-based fallback when LLM parsing is unavailable or too generic
- Action item normalization that separates owner names from task titles
- SQLite persistence for meetings, action items, task records, and follow-up logs
- Editable action items for owner, deadline, and status
- Feishu webhook integration with interactive summary and follow-up cards
- Manual follow-up reminders for unfinished action items
- Automatic scheduled follow-up scanning
- Duplicate reminder protection for same-day follow-up sends
- Chinese deadline parsing for common expressions such as:
  - `今天`
  - `明天`
  - `后天`
  - `周三`
  - `本周五`
  - `下周一`
  - `明天下午前`
  - `本周五下班前`
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

ACTIONBRIDGE_AUTO_FOLLOW_UP_ENABLED=true
ACTIONBRIDGE_AUTO_FOLLOW_UP_HOUR=10
ACTIONBRIDGE_AUTO_FOLLOW_UP_MINUTE=0
ACTIONBRIDGE_AUTO_FOLLOW_UP_POLL_SECONDS=30
```

## Run the Backend

From the `backend` directory:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The backend starts at:

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

The frontend starts at:

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
7. Click `发送当前会议跟进提醒` to push a follow-up card for unfinished action items in the current meeting.
8. Click `运行批量跟进` to scan all meetings and send reminders for due-today or overdue unfinished tasks.
9. Enable scheduled follow-up in `.env` if you want the backend to run the same scan automatically every day.

## Notes on Parsing

The parser currently supports:

- DeepSeek as the default provider
- OpenAI as an alternative provider
- Rule-based fallback when:
  - no valid API key is configured
  - the provider call fails
  - the LLM response is too generic to be useful

This keeps the MVP stable during demos and local development while still allowing higher-quality extraction when LLM calls succeed.

## Roadmap

Planned next steps include:

- stronger natural-language deadline parsing
- richer Feishu card interactions
- meeting-to-task execution tracking
- parser mode visibility in the UI
- stronger long-term memory and workflow orchestration

## Resume-Friendly Summary

ActionBridge is designed as a practical B-end productivity tool rather than a pure AI demo. It reduces manual work after meetings by turning discussion into structured tasks, syncing them into collaboration tools, and following up on unfinished work automatically.
