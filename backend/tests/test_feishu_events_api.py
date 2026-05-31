from datetime import UTC, datetime

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


def _meeting_event(message_id: str = "om_test_1") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "message_type": "text",
                "content": '{"text": "/meeting 每周产品同步会\\n讨论官网改版上线风险。\\nAction: 前端同学修复移动端问题。"}',
            }
        },
    }


def _done_event(action_item_id: int, message_id: str = "om_done_1") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "message_type": "text",
                "content": f'{{"text": "/done {action_item_id}"}}',
            }
        },
    }


def _tasks_event(message_id: str = "om_tasks_1") -> dict:
    return {
        "header": {"event_id": message_id},
        "event": {
            "message": {
                "message_id": message_id,
                "message_type": "text",
                "content": '{"text": "/tasks"}',
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

    accepted_commands: list[tuple[str, str]] = []

    def fake_process(title: str, transcript: str) -> None:
        accepted_commands.append((title, transcript))

    monkeypatch.setattr(routes, "process_feishu_meeting_command", fake_process)

    response = client.post("/api/feishu/events", json=_meeting_event())

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert accepted_commands[0][0] == "每周产品同步会"
    assert "讨论官网改版上线风险" in accepted_commands[0][1]


def test_feishu_events_deduplicates_meeting_command(client, monkeypatch) -> None:
    import app.api.routes as routes

    process_count = 0

    def fake_process(_title: str, _transcript: str) -> None:
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

    def fake_send(action_id: int, _title: str, _owner_name: str) -> str:
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

    def fake_send(_action_id: int, _title: str, _owner_name: str) -> str:
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


def test_feishu_events_done_missing_action_item_returns_404(client, monkeypatch) -> None:
    import app.api.routes as routes

    monkeypatch.setattr(routes, "send_action_item_completed_notice", lambda *_args: "sent")

    response = client.post("/api/feishu/events", json=_done_event(9999))

    assert response.status_code == 404
    assert response.json()["detail"] == "Action item not found"


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

    def fake_send(items) -> str:
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
    monkeypatch.setattr(routes, "send_open_tasks_summary", lambda items: sent_batches.append(list(items)) or "sent")

    response = client.post("/api/feishu/events", json=_tasks_event())

    assert response.status_code == 200
    assert response.json()["status"] == "listed"
    assert response.json()["task_count"] == 0
    assert sent_batches == [[]]


def test_feishu_events_deduplicates_tasks_command(client, monkeypatch) -> None:
    import app.api.routes as routes

    sent_count = 0

    def fake_send(_items) -> str:
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
