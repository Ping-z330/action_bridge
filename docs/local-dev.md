# Local Development

## Requirements

- Python 3.12+
- Node.js 18+
- npm

## Environment Variables

Create `.env` in the project root. You can start from `.env.example`.

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
ACTIONBRIDGE_PARSER_PROVIDER=deepseek

FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=your_feishu_app_secret
FEISHU_DEFAULT_CHAT_ID=oc_xxx

ACTIONBRIDGE_AUTO_FOLLOW_UP_ENABLED=false
ACTIONBRIDGE_AUTO_FOLLOW_UP_HOUR=10
ACTIONBRIDGE_AUTO_FOLLOW_UP_MINUTE=0
ACTIONBRIDGE_AUTO_FOLLOW_UP_POLL_SECONDS=30
```

Do not commit `.env` to GitHub.

## Start Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend:

```text
http://localhost:8000
```

Swagger:

```text
http://localhost:8000/docs
```

## Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend:

```text
http://localhost:3000
```

## Run Tests

Backend:

```bash
python -m pytest backend/tests
```

Frontend build:

```bash
cd frontend
npm run build
```

On Windows PowerShell, if `npm run build` is blocked by execution policy, use:

```bash
npm.cmd run build
```

## Feishu Local Callback

Feishu needs a public URL for event subscription. For local development, expose the backend:

```text
local FastAPI http://localhost:8000
  -> ngrok/cpolar public URL
  -> https://your-public-domain/api/feishu/events
```

Configure that URL in Feishu event subscription settings.

## Demo Checklist

1. Start backend.
2. Start frontend.
3. Open `http://localhost:3000`.
4. Create a meeting from pasted transcript or uploaded text file.
5. Open the meeting detail page.
6. Edit action item owner, deadline, or status.
7. Open `/tasks` to view grouped tasks.
8. Open `/history` to view historical statistics.
9. Send `/help` in Feishu.
10. Send `/meeting` in Feishu to create a meeting from chat.
11. Send `/tasks` or a natural-language task query.
12. Open `/agent-debug` to inspect Agent traces.
