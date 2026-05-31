from datetime import UTC, datetime

import pytest

from app.schemas.meeting import MeetingCreate, MeetingResponse
from app.services import feishu_event_service


@pytest.fixture(autouse=True)
def clear_feishu_event_dedup_cache() -> None:
    feishu_event_service._PROCESSED_EVENT_IDS.clear()


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
        "header": {"event_id": "event_test_1"},
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


def test_feishu_events_returns_challenge(client) -> None:
    response = client.post("/api/feishu/events", json={"challenge": "verify-token"})

    assert response.status_code == 200
    assert response.json() == {"challenge": "verify-token"}


def test_feishu_events_ignores_non_meeting_message(client) -> None:
    response = client.post(
        "/api/feishu/events",
        json={
            "event": {
                "message": {
                    "message_type": "text",
                    "content": '{"text": "普通群聊消息"}',
                }
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_feishu_events_creates_meeting_from_command(client, monkeypatch) -> None:
    import app.api.routes as routes

    captured_payload: dict[str, MeetingCreate] = {}
    sent_meetings: list[MeetingResponse] = []

    def fake_create(_db, payload: MeetingCreate) -> MeetingResponse:
        captured_payload["payload"] = payload
        return _fake_meeting()

    def fake_send(meeting: MeetingResponse) -> str:
        sent_meetings.append(meeting)
        return "sent"

    monkeypatch.setattr(routes, "create_meeting_with_actions", fake_create)
    monkeypatch.setattr(routes, "send_meeting_summary", fake_send)

    response = client.post("/api/feishu/events", json=_meeting_event())

    assert response.status_code == 200
    assert response.json()["status"] == "created"
    assert response.json()["meeting_id"] == 123
    assert captured_payload["payload"].title == "每周产品同步会"
    assert "讨论官网改版上线风险" in captured_payload["payload"].transcript
    assert sent_meetings[0].id == 123


def test_feishu_events_ignores_duplicate_message_id(client, monkeypatch) -> None:
    import app.api.routes as routes

    create_count = 0

    def fake_create(_db, _payload: MeetingCreate) -> MeetingResponse:
        nonlocal create_count
        create_count += 1
        return _fake_meeting()

    monkeypatch.setattr(routes, "create_meeting_with_actions", fake_create)
    monkeypatch.setattr(routes, "send_meeting_summary", lambda meeting: "sent")

    first_response = client.post("/api/feishu/events", json=_meeting_event(message_id="om_duplicate"))
    second_response = client.post("/api/feishu/events", json=_meeting_event(message_id="om_duplicate"))

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "created"
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "duplicated"
    assert create_count == 1


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
