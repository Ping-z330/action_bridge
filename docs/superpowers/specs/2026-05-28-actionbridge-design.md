# ActionBridge MVP Design

## Goal

ActionBridge converts meeting transcripts into structured action items and supports a lightweight execution loop through a web dashboard and Feishu delivery endpoint.

## MVP Scope

The first version focuses on a single end-to-end flow:

1. A user submits a meeting title and transcript.
2. The backend parses the transcript into a summary, decisions, and action items.
3. The system stores the meeting and action items.
4. The frontend displays the parsed meeting result.
5. A user can trigger a Feishu delivery endpoint for the current meeting.

The MVP intentionally excludes automatic speech-to-text, asynchronous workers, full multi-agent autonomy, and deep Feishu workflow integration.

## Architecture

The project is split into two applications:

- `backend/`: FastAPI service for APIs, parsing workflow, persistence, and Feishu delivery placeholder.
- `frontend/`: Next.js app for transcript submission and meeting detail viewing.

The initial persistence layer uses SQLite to minimize setup friction. The data model is shaped so that PostgreSQL can replace SQLite later with minimal changes.

## Components

### Backend

- `api/`: HTTP endpoints for meeting creation, meeting listing, meeting detail, and Feishu sending.
- `db/`: SQLAlchemy engine, session management, and table bootstrap.
- `models/`: Meeting, action item, and task ORM models.
- `schemas/`: Request and response models for API validation.
- `services/`: Transcript parser and meeting orchestration logic.
- `core/`: Configuration helpers.

### Frontend

- `app/`: App Router pages for dashboard and meeting detail.
- `components/`: Reusable form and detail display components.
- `lib/`: API client helpers and shared TypeScript types.

## Data Flow

1. Frontend sends a meeting title and transcript to `POST /api/meetings`.
2. Backend creates a task record for parsing.
3. Parser service returns a deterministic structured result using a placeholder extraction strategy.
4. Backend writes the meeting summary and action items.
5. Frontend fetches meetings and details through read endpoints.
6. User triggers `POST /api/meetings/{id}/send-feishu` to simulate external notification.

## Error Handling

- Empty title or transcript is rejected at request validation time.
- Missing meetings return `404`.
- Parsing failures mark the related task as `failed` and return a `500`.
- Feishu send failures are currently represented through a response payload and can later be replaced with actual API integration.

## Testing Strategy

- Backend unit tests should cover parser output shape and meeting creation flow.
- API tests should cover create, list, detail, and send-to-Feishu endpoints.
- Frontend smoke checks should verify transcript submission, meeting listing, and detail rendering.

## Open Assumptions

- Transcript input is pasted or uploaded outside this MVP and sent as plain text.
- Feishu integration starts as a placeholder response, not a production bot integration.
- Meeting decisions are stored as JSON on the meeting record in the MVP to reduce table count.
