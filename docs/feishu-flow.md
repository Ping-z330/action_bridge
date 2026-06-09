# Feishu Flow

This document explains how Feishu connects to ActionBridge.

## Connection Model

Feishu sends events to the backend through an event callback URL:

```text
Feishu -> POST /api/feishu/events -> ActionBridge backend
```

ActionBridge replies by calling Feishu Webhook or Feishu App Bot APIs:

```text
ActionBridge backend -> Feishu Webhook / OpenAPI -> Feishu chat
```

## Event Entry

The backend entry point is:

```text
POST /api/feishu/events
```

Main files:

```text
backend/app/api/routes.py
backend/app/services/feishu_event_router.py
backend/app/services/feishu_event_service.py
backend/app/services/feishu_event_guard.py
backend/app/services/feishu_command_handler.py
backend/app/services/feishu_service.py
```

## URL Verification

When Feishu verifies the event URL, it sends a `challenge`.

```text
Feishu challenge
  -> extract_challenge()
  -> backend returns challenge
```

After this succeeds, Feishu will start sending message events to the backend.

## Fixed Command Flow

Example:

```text
/done 12
```

Flow:

```text
Feishu message
  -> /api/feishu/events
  -> feishu_event_router.py
  -> feishu_command_handler.py
  -> meeting_service.py
  -> SQLite action_items
  -> feishu_service.py
  -> Feishu card response
```

Supported fixed commands:

```text
/meeting <title>
meeting transcript...

/tasks
/task <action_item_id>
/done <action_item_id>
/help
/remember <alias> = <target>
/memory
/forget <alias>
/bind-channel <project_keyword>
```

## Natural-Language Agent Flow

Example:

```text
@ActionBridge show today's due tasks
```

Flow:

```text
Feishu message
  -> /api/feishu/events
  -> feishu_event_router.py
  -> feishu_event_guard.py
  -> memory_service.py
  -> agent/orchestrator.py
  -> agent/graph.py
  -> intent detection
  -> tool execution
  -> response builder
  -> feishu_service.py
  -> Feishu card response
```

## Group Chat Guard

Private chat:

```text
Natural-language messages are processed by default.
```

Group chat:

```text
Fixed commands are processed.
Natural-language messages require @ActionBridge.
Pending confirmation replies are allowed.
Other group messages are ignored.
```

This prevents the bot from responding to every normal group message.

## Pending Confirmation Flow

Some operations are intentionally not executed immediately:

```text
create task
change deadline
change owner
```

Flow:

```text
User asks for a write operation
  -> Agent extracts intent
  -> backend saves PendingAgentAction
  -> Feishu sends confirmation card/message
  -> user replies confirm or cancel
  -> backend executes or cancels
```

The user can also revise a pending action before confirming:

```text
Change task 12 deadline to Friday
Change it to next Monday
Confirm
```

## Feishu Sending Modes

Preferred mode: Feishu App Bot

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=your_feishu_app_secret
FEISHU_DEFAULT_CHAT_ID=oc_xxx
```

Fallback mode: Feishu Webhook

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id
```

## Project Channel Sync

Use:

```text
/bind-channel website redesign
```

When a completed task matches the project keyword, ActionBridge can sync the completion notice to the bound Feishu group.
