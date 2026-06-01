from datetime import UTC, date, datetime

from app.schemas.meeting import MeetingResponse


def _fake_meeting() -> MeetingResponse:
    return MeetingResponse(
        id=123,
        title="每周产品同步会",
        raw_transcript="讨论官网改版上线风险。",
        summary="本次会议讨论了官网改版上线风险。",
        decisions=["官网改版按计划推进。"],
        created_at=datetime(2026, 5, 30, 8, 0, tzinfo=UTC),
        action_items=[],
    )


def _meeting_event(message_id: str = "om_test_1", chat_id: str = "oc_source") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": "text",
                "content": '{"text": "/meeting 每周产品同步会\\n讨论官网改版上线风险。\\nAction: 前端同学修复移动端问题。"}',
            }
        },
    }


def _done_event(action_item_id: int, message_id: str = "om_done_1", chat_id: str = "oc_source") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": "text",
                "content": f'{{"text": "/done {action_item_id}"}}',
            }
        },
    }


def _tasks_event(message_id: str = "om_tasks_1", chat_id: str = "oc_source") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": "text",
                "content": '{"text": "/tasks"}',
            }
        },
    }


def _help_event(message_id: str = "om_help_1", chat_id: str = "oc_source") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": "text",
                "content": '{"text": "/help"}',
            }
        },
    }


def _remember_event(text: str, message_id: str = "om_remember_1", chat_id: str = "oc_source") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": "text",
                "content": f'{{"text": "{text}"}}',
            }
        },
    }


def _memory_event(message_id: str = "om_memory_1", chat_id: str = "oc_source") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": "text",
                "content": '{"text": "/memory"}',
            }
        },
    }


def _forget_event(alias: str, message_id: str = "om_forget_1", chat_id: str = "oc_source") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": "text",
                "content": f'{{"text": "/forget {alias}"}}',
            }
        },
    }


def _natural_language_event(text: str, message_id: str = "om_agent_1", chat_id: str = "oc_source") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": "text",
                "content": f'{{"text": "{text}"}}',
            }
        },
    }


def _task_event(action_item_id: int | str, message_id: str = "om_task_1", chat_id: str = "oc_source") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": "text",
                "content": f'{{"text": "/task {action_item_id}"}}',
            }
        },
    }


def test_feishu_events_returns_challenge(client) -> None:
    response = client.post("/api/feishu/events", json={"challenge": "verify-token"})

    assert response.status_code == 200
    assert response.json() == {"challenge": "verify-token"}


def test_feishu_events_ignores_non_command_message(client) -> None:
    response = client.post(
        "/api/feishu/events",
        json={"event": {"message": {"message_type": "text", "content": '{"text": "普通群聊消息"}'}}},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_feishu_events_accepts_meeting_command_in_background(client, monkeypatch) -> None:
    import app.api.routes as routes

    accepted_commands: list[tuple[str, str, str | None]] = []

    def fake_process(title: str, transcript: str, receive_id: str | None = None) -> None:
        accepted_commands.append((title, transcript, receive_id))

    monkeypatch.setattr(routes, "process_feishu_meeting_command", fake_process)

    response = client.post("/api/feishu/events", json=_meeting_event())

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert accepted_commands[0][0] == "每周产品同步会"
    assert "讨论官网改版上线风险" in accepted_commands[0][1]


def test_feishu_events_deduplicates_meeting_command(client, monkeypatch) -> None:
    import app.api.routes as routes

    process_count = 0

    def fake_process(_title: str, _transcript: str, _receive_id: str | None = None) -> None:
        nonlocal process_count
        process_count += 1

    monkeypatch.setattr(routes, "process_feishu_meeting_command", fake_process)

    first_response = client.post("/api/feishu/events", json=_meeting_event(message_id="om_duplicate"))
    second_response = client.post("/api/feishu/events", json=_meeting_event(message_id="om_duplicate"))

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "accepted"
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "duplicated"
    assert process_count == 1


def test_feishu_events_marks_action_item_done(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "任务完成测试会",
            "transcript": "Action: 前端同学更新落地页文案",
        },
    )
    meeting = create_response.json()
    action_item_id = meeting["action_items"][0]["id"]
    sent_notices: list[int] = []

    def fake_send(action_id: int, _title: str, _owner_name: str, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_notices.append(action_id)
        return "sent"

    monkeypatch.setattr(routes, "send_action_item_completed_notice", fake_send)

    response = client.post("/api/feishu/events", json=_done_event(action_item_id))

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["action_item_id"] == action_item_id
    assert sent_notices == [action_item_id]

    detail_response = client.get(f"/api/meetings/{meeting['id']}")
    updated_item = detail_response.json()["action_items"][0]
    assert updated_item["status"] == "completed"


def test_feishu_events_deduplicates_done_command(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "重复完成测试会",
            "transcript": "Action: 测试同学补充回归用例",
        },
    )
    action_item_id = create_response.json()["action_items"][0]["id"]
    sent_count = 0

    def fake_send(_action_id: int, _title: str, _owner_name: str, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        nonlocal sent_count
        sent_count += 1
        return "sent"

    monkeypatch.setattr(routes, "send_action_item_completed_notice", fake_send)

    first_response = client.post("/api/feishu/events", json=_done_event(action_item_id, message_id="om_done_dup"))
    second_response = client.post("/api/feishu/events", json=_done_event(action_item_id, message_id="om_done_dup"))

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "completed"
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "duplicated"
    assert sent_count == 1


def test_feishu_events_done_missing_action_item_sends_notice(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_ids = []

    def fake_send(action_item_id: int, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_ids.append(action_item_id)
        return "sent"

    monkeypatch.setattr(routes, "send_task_not_found_notice", fake_send)

    response = client.post("/api/feishu/events", json=_done_event(9999))

    assert response.status_code == 200
    assert response.json()["status"] == "task_not_found"
    assert response.json()["action_item_id"] == 9999
    assert sent_ids == [9999]


def test_feishu_events_lists_open_tasks(client, monkeypatch) -> None:
    import app.api.routes as routes

    client.post(
        "/api/meetings",
        json={
            "title": "任务列表测试会",
            "transcript": "\n".join(
                [
                    "Action: 前端同学修复移动端问题",
                    "Action: 测试同学补充回归用例",
                ]
            ),
        },
    )
    sent_batches = []

    def fake_send(items, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        materialized = list(items)
        sent_batches.append(materialized)
        return "sent"

    monkeypatch.setattr(routes, "send_open_tasks_summary", fake_send)

    response = client.post("/api/feishu/events", json=_tasks_event())

    assert response.status_code == 200
    assert response.json()["status"] == "listed"
    assert response.json()["task_count"] == 2
    assert len(sent_batches[0]) == 2
    assert sent_batches[0][0].status != "completed"


def test_feishu_events_lists_empty_open_tasks(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_batches = []
    monkeypatch.setattr(
        routes,
        "send_open_tasks_summary",
        lambda items, receive_id=None: sent_batches.append(list(items)) or "sent",
    )

    response = client.post("/api/feishu/events", json=_tasks_event())

    assert response.status_code == 200
    assert response.json()["status"] == "listed"
    assert response.json()["task_count"] == 0
    assert sent_batches == [[]]


def test_feishu_events_sends_help_card_for_help_command(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_receive_ids = []

    def fake_send(receive_id: str | None = None) -> str:
        sent_receive_ids.append(receive_id)
        return "sent"

    monkeypatch.setattr(routes, "send_help_card", fake_send)

    response = client.post("/api/feishu/events", json=_help_event())

    assert response.status_code == 200
    assert response.json()["status"] == "help_sent"
    assert sent_receive_ids == ["oc_source"]


def test_feishu_events_remembers_lists_and_forgets_alias(client, monkeypatch) -> None:
    import app.api.routes as routes

    saved_items = []
    listed_batches = []
    deleted_items = []

    def fake_saved(item, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        saved_items.append(item)
        return "sent"

    def fake_list(items, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        listed_batches.append(list(items))
        return "sent"

    def fake_deleted(item, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        deleted_items.append(item)
        return "sent"

    monkeypatch.setattr(routes, "send_memory_saved_notice", fake_saved)
    monkeypatch.setattr(routes, "send_memory_list_summary", fake_list)
    monkeypatch.setattr(routes, "send_memory_deleted_notice", fake_deleted)

    remember_response = client.post("/api/feishu/events", json=_remember_event("/remember project 官网 = 官网改版"))
    list_response = client.post("/api/feishu/events", json=_memory_event())
    forget_response = client.post("/api/feishu/events", json=_forget_event("官网"))

    assert remember_response.status_code == 200
    assert remember_response.json()["status"] == "memory_saved"
    assert remember_response.json()["alias"] == "官网"
    assert remember_response.json()["target"] == "官网改版"
    assert saved_items[0].memory_type == "project"

    assert list_response.status_code == 200
    assert list_response.json()["status"] == "memory_listed"
    assert list_response.json()["memory_count"] == 1
    assert listed_batches[0][0].alias == "官网"

    assert forget_response.status_code == 200
    assert forget_response.json()["status"] == "memory_deleted"
    assert deleted_items[0].alias == "官网"


def test_feishu_events_sends_single_task_detail(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Single task detail test",
            "transcript": "Action: Frontend updates landing page copy before Friday.",
        },
    )
    action_item_id = create_response.json()["action_items"][0]["id"]
    sent_items = []

    def fake_send(item, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_items.append(item)
        return "sent"

    monkeypatch.setattr(routes, "send_task_detail_summary", fake_send)

    response = client.post("/api/feishu/events", json=_task_event(action_item_id))

    assert response.status_code == 200
    assert response.json()["status"] == "task_found"
    assert response.json()["action_item_id"] == action_item_id
    assert sent_items[0].id == action_item_id


def test_feishu_events_deduplicates_single_task_command(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Single task duplicate test",
            "transcript": "Action: QA supplements regression cases.",
        },
    )
    action_item_id = create_response.json()["action_items"][0]["id"]
    sent_count = 0

    def fake_send(_item, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        nonlocal sent_count
        sent_count += 1
        return "sent"

    monkeypatch.setattr(routes, "send_task_detail_summary", fake_send)

    first_response = client.post("/api/feishu/events", json=_task_event(action_item_id, message_id="om_task_dup"))
    second_response = client.post("/api/feishu/events", json=_task_event(action_item_id, message_id="om_task_dup"))

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "task_found"
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "duplicated"
    assert sent_count == 1


def test_feishu_events_task_missing_action_item_sends_notice(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_ids = []

    def fake_send(action_item_id: int, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_ids.append(action_item_id)
        return "sent"

    monkeypatch.setattr(routes, "send_task_not_found_notice", fake_send)

    response = client.post("/api/feishu/events", json=_task_event(9999))

    assert response.status_code == 200
    assert response.json()["status"] == "task_not_found"
    assert response.json()["action_item_id"] == 9999
    assert sent_ids == [9999]


def test_feishu_events_rejects_invalid_task_command(client) -> None:
    response = client.post("/api/feishu/events", json=_task_event("abc"))

    assert response.status_code == 400
    assert "Invalid /task command" in response.json()["detail"]


def test_feishu_events_agent_lists_due_today_tasks(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Agent natural language test",
            "transcript": "Action: Frontend fixes mobile navigation issue.",
        },
    )
    meeting = create_response.json()
    action_item_id = meeting["action_items"][0]["id"]
    today = date.today().isoformat()
    client.patch(
        f"/api/action-items/{action_item_id}",
        json={
            "owner_name": "前端同学",
            "deadline": "今天 18:00",
            "deadline_date": today,
            "deadline_time": "18:00",
            "status": "pending",
        },
    )
    sent_batches = []

    def fake_send(items, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_batches.append(list(items))
        return "sent"

    monkeypatch.setattr(routes, "send_open_tasks_summary", fake_send)

    response = client.post("/api/feishu/events", json=_natural_language_event("帮我看看今天到期的任务"))

    assert response.status_code == 200
    assert response.json()["status"] == "agent_replied"
    assert response.json()["intent"] == "query_tasks"
    assert response.json()["task_count"] == 1
    assert sent_batches[0][0].id == action_item_id


def test_feishu_events_agent_updates_task_status(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Agent update test",
            "transcript": "Action: Frontend fixes mobile navigation issue.",
        },
    )
    meeting = create_response.json()
    action_item_id = meeting["action_items"][0]["id"]
    sent_items = []

    def fake_send(item, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_items.append(item)
        return "sent"

    monkeypatch.setattr(routes, "send_task_detail_summary", fake_send)

    response = client.post("/api/feishu/events", json=_natural_language_event(f"把 {action_item_id} 号任务标记完成"))

    assert response.status_code == 200
    assert response.json()["status"] == "agent_updated"
    assert response.json()["intent"] == "update_task_status"
    assert response.json()["action_item_id"] == action_item_id
    assert response.json()["target_status"] == "completed"
    assert sent_items[0].id == action_item_id
    assert sent_items[0].status == "completed"

    detail_response = client.get(f"/api/meetings/{meeting['id']}")
    updated_item = detail_response.json()["action_items"][0]
    assert updated_item["status"] == "completed"


def test_feishu_events_agent_asks_confirmation_before_creating_task(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_confirmations = []

    def fake_send(title: str, owner_name: str, deadline: str, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_confirmations.append((title, owner_name, deadline))
        return "sent"

    monkeypatch.setattr(routes, "send_task_create_confirmation", fake_send)

    response = client.post(
        "/api/feishu/events",
        json=_natural_language_event("帮我加一个任务，前端同学周五前完成登录页联调", message_id="om_create_task"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "task_create_pending"
    assert response.json()["intent"] == "create_task"
    assert sent_confirmations == [("登录页联调", "前端同学", "周五前")]
    assert client.get("/api/action-items").json() == []


def test_feishu_events_agent_creates_task_after_confirmation(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_items = []

    monkeypatch.setattr(routes, "send_task_create_confirmation", lambda *_args, **_kwargs: "sent")

    def fake_send(item, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_items.append(item)
        return "sent"

    monkeypatch.setattr(routes, "send_task_detail_summary", fake_send)

    pending_response = client.post(
        "/api/feishu/events",
        json=_natural_language_event("帮我加一个任务，前端同学周五前完成登录页联调", message_id="om_create_task"),
    )
    confirm_response = client.post(
        "/api/feishu/events",
        json=_natural_language_event("确认", message_id="om_confirm_create_task"),
    )

    assert pending_response.status_code == 200
    assert pending_response.json()["status"] == "task_create_pending"
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "agent_confirmed"
    assert confirm_response.json()["intent"] == "confirm_create_task"
    assert sent_items[0].title == "登录页联调"
    assert sent_items[0].owner_name == "前端同学"
    assert sent_items[0].deadline_date
    assert sent_items[0].deadline_time == "18:00"
    assert sent_items[0].meeting_title == "飞书临时任务"

    tasks_response = client.get("/api/action-items")
    created = [item for item in tasks_response.json() if item["id"] == confirm_response.json()["action_item_id"]][0]
    assert created["title"] == "登录页联调"
    assert created["status"] == "pending"


def test_feishu_events_agent_cancels_pending_create_task(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_notices = []

    monkeypatch.setattr(routes, "send_task_create_confirmation", lambda *_args, **_kwargs: "sent")

    def fake_notice(title: str, message: str, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_notices.append((title, message))
        return "sent"

    monkeypatch.setattr(routes, "send_pending_action_notice", fake_notice)

    client.post(
        "/api/feishu/events",
        json=_natural_language_event("帮我加一个任务，前端同学周五前完成登录页联调", message_id="om_create_task"),
    )
    response = client.post(
        "/api/feishu/events",
        json=_natural_language_event("取消", message_id="om_cancel_create_task"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending_cancelled"
    assert "已取消" in sent_notices[0][0]
    assert client.get("/api/action-items").json() == []


def test_feishu_events_agent_asks_confirmation_before_updating_deadline(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Deadline update confirmation test",
            "transcript": "Action: Frontend fixes mobile navigation issue.",
        },
    )
    action_item_id = create_response.json()["action_items"][0]["id"]
    sent_confirmations = []

    def fake_send(
        action_item_id: int,
        title: str,
        old_deadline: str,
        new_deadline: str,
        receive_id: str | None = None,
    ) -> str:
        assert receive_id == "oc_source"
        sent_confirmations.append((action_item_id, title, old_deadline, new_deadline))
        return "sent"

    monkeypatch.setattr(routes, "send_task_deadline_update_confirmation", fake_send)

    response = client.post(
        "/api/feishu/events",
        json=_natural_language_event(f"把 {action_item_id} 号任务延期到周五", message_id="om_update_deadline"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "task_deadline_update_pending"
    assert response.json()["intent"] == "update_task_deadline"
    assert sent_confirmations[0][0] == action_item_id
    assert sent_confirmations[0][3] == "周五"

    unchanged = client.get(f"/api/meetings/{create_response.json()['id']}").json()["action_items"][0]
    assert unchanged["deadline"] == sent_confirmations[0][2]


def test_feishu_events_agent_updates_deadline_after_confirmation(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Deadline update execution test",
            "transcript": "Action: Frontend fixes mobile navigation issue.",
        },
    )
    meeting = create_response.json()
    action_item_id = meeting["action_items"][0]["id"]
    sent_items = []

    monkeypatch.setattr(routes, "send_task_deadline_update_confirmation", lambda *_args, **_kwargs: "sent")

    def fake_send(item, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_items.append(item)
        return "sent"

    monkeypatch.setattr(routes, "send_task_detail_summary", fake_send)

    pending_response = client.post(
        "/api/feishu/events",
        json=_natural_language_event(f"把 {action_item_id} 号任务延期到周五", message_id="om_update_deadline"),
    )
    confirm_response = client.post(
        "/api/feishu/events",
        json=_natural_language_event("确认", message_id="om_confirm_update_deadline"),
    )

    assert pending_response.status_code == 200
    assert pending_response.json()["status"] == "task_deadline_update_pending"
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "agent_confirmed"
    assert confirm_response.json()["intent"] == "confirm_update_task_deadline"
    assert confirm_response.json()["action_item_id"] == action_item_id
    assert sent_items[0].id == action_item_id
    assert sent_items[0].deadline_date
    assert sent_items[0].deadline_time == "18:00"

    updated = client.get(f"/api/meetings/{meeting['id']}").json()["action_items"][0]
    assert updated["deadline_date"]
    assert updated["deadline_time"] == "18:00"


def test_feishu_events_agent_asks_confirmation_before_updating_owner(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Owner update confirmation test",
            "transcript": "Action: 前端同学修复移动端问题。",
        },
    )
    meeting = create_response.json()
    action_item_id = meeting["action_items"][0]["id"]
    original_owner = meeting["action_items"][0]["owner_name"]
    sent_confirmations = []

    def fake_send(
        action_item_id: int,
        title: str,
        old_owner_name: str,
        new_owner_name: str,
        receive_id: str | None = None,
    ) -> str:
        assert receive_id == "oc_source"
        sent_confirmations.append((action_item_id, title, old_owner_name, new_owner_name))
        return "sent"

    monkeypatch.setattr(routes, "send_task_owner_update_confirmation", fake_send)

    response = client.post(
        "/api/feishu/events",
        json=_natural_language_event(f"把 {action_item_id} 号任务负责人改成测试同学", message_id="om_update_owner"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "task_owner_update_pending"
    assert response.json()["intent"] == "update_task_owner"
    assert sent_confirmations[0][0] == action_item_id
    assert sent_confirmations[0][2] == original_owner
    assert sent_confirmations[0][3] == "测试同学"

    unchanged = client.get(f"/api/meetings/{meeting['id']}").json()["action_items"][0]
    assert unchanged["owner_name"] == original_owner


def test_feishu_events_agent_updates_owner_after_confirmation(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Owner update execution test",
            "transcript": "Action: 前端同学修复移动端问题。",
        },
    )
    meeting = create_response.json()
    action_item_id = meeting["action_items"][0]["id"]
    sent_items = []

    monkeypatch.setattr(routes, "send_task_owner_update_confirmation", lambda *_args, **_kwargs: "sent")

    def fake_send(item, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_items.append(item)
        return "sent"

    monkeypatch.setattr(routes, "send_task_detail_summary", fake_send)

    pending_response = client.post(
        "/api/feishu/events",
        json=_natural_language_event(f"把 {action_item_id} 号任务负责人改成测试同学", message_id="om_update_owner"),
    )
    confirm_response = client.post(
        "/api/feishu/events",
        json=_natural_language_event("确认", message_id="om_confirm_update_owner"),
    )

    assert pending_response.status_code == 200
    assert pending_response.json()["status"] == "task_owner_update_pending"
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "agent_confirmed"
    assert confirm_response.json()["intent"] == "confirm_update_task_owner"
    assert confirm_response.json()["action_item_id"] == action_item_id
    assert sent_items[0].id == action_item_id
    assert sent_items[0].owner_name == "测试同学"

    updated = client.get(f"/api/meetings/{meeting['id']}").json()["action_items"][0]
    assert updated["owner_name"] == "测试同学"


def test_feishu_events_agent_update_deadline_missing_action_item_sends_notice(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_ids = []

    def fake_send(action_item_id: int, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_ids.append(action_item_id)
        return "sent"

    monkeypatch.setattr(routes, "send_task_not_found_notice", fake_send)

    response = client.post(
        "/api/feishu/events",
        json=_natural_language_event("把 9999 号任务延期到周五", message_id="om_missing_deadline_update"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "task_not_found"
    assert response.json()["action_item_id"] == 9999
    assert sent_ids == [9999]


def test_feishu_events_agent_update_owner_missing_action_item_sends_notice(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_ids = []

    def fake_send(action_item_id: int, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_ids.append(action_item_id)
        return "sent"

    monkeypatch.setattr(routes, "send_task_not_found_notice", fake_send)

    response = client.post(
        "/api/feishu/events",
        json=_natural_language_event("把 9999 号任务负责人改成测试同学", message_id="om_missing_owner_update"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "task_not_found"
    assert response.json()["action_item_id"] == 9999
    assert sent_ids == [9999]


def test_feishu_events_agent_create_task_missing_info_prompts_user(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_messages = []

    def fake_send(message: str, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_messages.append(message)
        return "sent"

    monkeypatch.setattr(routes, "send_task_create_clarification", fake_send)

    response = client.post(
        "/api/feishu/events",
        json=_natural_language_event("创建任务：登录页联调", message_id="om_create_task_missing"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "task_create_needs_info"
    assert response.json()["intent"] == "create_task_missing_info"
    assert "负责人" in sent_messages[0]
    assert "截止时间" in sent_messages[0]
    assert client.get("/api/action-items").json() == []


def test_feishu_events_agent_update_missing_action_item_sends_notice(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_ids = []

    def fake_send(action_item_id: int, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_ids.append(action_item_id)
        return "sent"

    monkeypatch.setattr(routes, "send_task_not_found_notice", fake_send)

    response = client.post("/api/feishu/events", json=_natural_language_event("把 9999 号任务标记完成"))

    assert response.status_code == 200
    assert response.json()["status"] == "task_not_found"
    assert response.json()["action_item_id"] == 9999
    assert sent_ids == [9999]


def test_feishu_events_agent_sends_project_progress_summary(client, monkeypatch) -> None:
    import app.api.routes as routes

    client.post(
        "/api/meetings",
        json={
            "title": "官网改版上线会",
            "transcript": "\n".join(
                [
                    "Action: Frontend fixes mobile navigation issue.",
                    "Action: QA supplements regression cases.",
                ]
            ),
        },
    )
    sent_summaries = []

    def fake_send(summary, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_summaries.append(summary)
        return "sent"

    monkeypatch.setattr(routes, "send_project_progress_summary", fake_send)

    response = client.post("/api/feishu/events", json=_natural_language_event("官网改版进度怎么样"))

    assert response.status_code == 200
    assert response.json()["status"] == "agent_replied"
    assert response.json()["intent"] == "summarize_project"
    assert response.json()["task_count"] == 2
    assert sent_summaries[0].keyword == "官网改版"
    assert sent_summaries[0].total_count == 2


def test_feishu_events_agent_uses_memory_alias_for_project_summary(client, monkeypatch) -> None:
    import app.api.routes as routes

    client.post(
        "/api/meetings",
        json={
            "title": "官网改版上线会",
            "transcript": "\n".join(
                [
                    "Action: Frontend fixes mobile navigation issue.",
                    "Action: QA supplements regression cases.",
                ]
            ),
        },
    )
    client.post("/api/feishu/events", json=_remember_event("/remember 官网 = 官网改版", message_id="om_remember_alias"))
    sent_summaries = []

    def fake_send(summary, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        sent_summaries.append(summary)
        return "sent"

    monkeypatch.setattr(routes, "send_project_progress_summary", fake_send)

    response = client.post("/api/feishu/events", json=_natural_language_event("官网进度怎么样", message_id="om_alias_query"))

    assert response.status_code == 200
    assert response.json()["status"] == "agent_replied"
    assert response.json()["intent"] == "summarize_project"
    assert response.json()["task_count"] == 2
    assert sent_summaries[0].keyword == "官网改版"


def test_feishu_events_agent_sends_help_card_for_natural_language(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_receive_ids = []

    def fake_send(receive_id: str | None = None) -> str:
        sent_receive_ids.append(receive_id)
        return "sent"

    monkeypatch.setattr(routes, "send_help_card", fake_send)

    response = client.post("/api/feishu/events", json=_natural_language_event("你能做什么", message_id="om_help_nl"))

    assert response.status_code == 200
    assert response.json()["status"] == "help_sent"
    assert response.json()["intent"] == "help"
    assert sent_receive_ids == ["oc_source"]


def test_feishu_events_agent_ignores_unrelated_chat(client) -> None:
    response = client.post("/api/feishu/events", json=_natural_language_event("大家下午好", message_id="om_agent_ignore"))

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_feishu_events_deduplicates_tasks_command(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_count = 0

    def fake_send(_items, receive_id: str | None = None) -> str:
        assert receive_id == "oc_source"
        nonlocal sent_count
        sent_count += 1
        return "sent"

    monkeypatch.setattr(routes, "send_open_tasks_summary", fake_send)

    first_response = client.post("/api/feishu/events", json=_tasks_event(message_id="om_tasks_dup"))
    second_response = client.post("/api/feishu/events", json=_tasks_event(message_id="om_tasks_dup"))

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "listed"
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "duplicated"
    assert sent_count == 1


def test_feishu_events_rejects_invalid_meeting_command(client) -> None:
    response = client.post(
        "/api/feishu/events",
        json={"text": "/meeting 只有标题没有正文"},
    )

    assert response.status_code == 400
    assert "Invalid /meeting command" in response.json()["detail"]


def test_feishu_events_rejects_invalid_done_command(client) -> None:
    response = client.post("/api/feishu/events", json={"text": "/done abc"})

    assert response.status_code == 400
    assert "Invalid /done command" in response.json()["detail"]
