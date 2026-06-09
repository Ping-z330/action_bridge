# ActionBridge Architecture

This document explains the main modules behind ActionBridge.

## High-Level Layers

```text
frontend/
  Next.js pages and React components

backend/app/api/
  FastAPI route entry points

backend/app/services/
  Business logic: meetings, Feishu, follow-up, memory, deadlines

backend/app/agent/
  Natural-language Agent flow, intent detection, tools, trace logging

backend/app/models/
  SQLAlchemy ORM database models

backend/app/schemas/
  Pydantic request and response models
```

## Main Data Flow

```text
User inputs meeting notes
  -> frontend/components/MeetingForm.tsx
  -> POST /api/meetings
  -> backend/app/api/routes.py
  -> backend/app/services/meeting_service.py
  -> backend/app/services/parser_service.py
  -> SQLite meetings / action_items
  -> frontend/components/MeetingDetail.tsx
```

## Frontend

```text
frontend/app/page.tsx
  Main meeting workspace.

frontend/app/tasks/page.tsx
  Task board grouped by meeting.

frontend/app/history/page.tsx
  Historical meeting records and execution statistics.

frontend/app/meetings/[id]/page.tsx
  Meeting detail page.

frontend/app/agent-debug/page.tsx
  Agent trace and manual debug page.
```

Important components:

```text
AppShell.tsx
  Shared navigation shell.

MeetingForm.tsx
  Meeting note input and file upload.

MeetingDetail.tsx
  Meeting summary, decisions, action item editing, Feishu sending.

TaskResults.tsx
  Task board, filtering, status update.

HistoryRecords.tsx
  Historical records and statistics.

AgentDebugPanel.tsx
  Manual Agent run and trace inspection.
```

## Backend Services

```text
meeting_service.py
  Creates meetings, stores action items, updates action items, sends Feishu summaries.

parser_service.py
  Parses transcripts through DeepSeek/OpenAI-compatible APIs or rule fallback.

deadline_service.py
  Normalizes natural-language deadlines into date/time fields.

due_status_service.py
  Classifies tasks as due_today, overdue, upcoming, unknown, or completed.

feishu_service.py
  Builds and sends Feishu cards.

feishu_event_service.py
  Extracts command data from Feishu payloads.

feishu_event_router.py
  Converts raw Feishu events into a unified context.

feishu_command_handler.py
  Handles fixed Feishu commands such as /tasks, /done, /task, /help.

follow_up_service.py
  Scans due/overdue tasks and sends follow-up reminders.

auto_follow_up_scheduler.py
  Runs follow-up scans on a schedule.

memory_service.py
  Stores and applies structured aliases.

project_channel_service.py
  Binds project keywords to Feishu groups and syncs completed tasks.
```

## Agent Modules

```text
graph.py
  Agent execution graph.

orchestrator.py
  Feishu-facing Agent orchestration and confirmation flow.

service.py
  Rule-based intent detection and fallback routing.

llm_intent_service.py
  LLM fallback for natural-language intent extraction.

task_reference_resolver.py
  Resolves references such as "the second task" or "that task".

tools.py
  Concrete task query/update/create/project-summary tools.

tool_registry.py
  Registry for local Agent tools.

tool_contracts.py
  Shared AgentTool and registry contracts.

agent_trace_service.py
  Stores trace logs for debugging.
```

## Database Tables

```text
meetings
  Meeting title, transcript, summary, decisions.

action_items
  Extracted tasks with owner, deadline, status, normalized deadline fields.

tasks
  Background task records.

follow_up_logs
  Follow-up reminder and reply records.

feishu_event_logs
  Feishu event deduplication.

memory_aliases
  Alias memory for project/team terminology.

pending_agent_actions
  Pending create/update actions waiting for user confirmation.

agent_trace_logs
  Agent debug traces.

agent_task_contexts
  Recent task list context for references like "the second task".

project_channels
  Project keyword to Feishu group binding.
```
