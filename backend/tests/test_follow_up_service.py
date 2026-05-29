from datetime import date, datetime, timedelta

from app.core.time import utc_now


def test_run_follow_ups_only_sends_due_today_or_overdue_items(client, monkeypatch) -> None:
    import app.services.follow_up_service as follow_up_service

    today = utc_now().date()
    overdue = (today - timedelta(days=1)).isoformat()
    due_today = today.isoformat()
    future = (today + timedelta(days=2)).isoformat()

    created = client.post(
        "/api/meetings",
        json={
            "title": "自动提醒测试",
            "transcript": "\n".join(
                [
                    "讨论上线节奏",
                    "Action: 前端同学更新活动页",
                    "Next step: 产品经理确认上线公告",
                    "Action: 测试同学补充回归测试",
                ]
            ),
        },
    ).json()

    items = created["action_items"]
    client.patch(
        f"/api/action-items/{items[0]['id']}",
        json={"owner_name": "前端同学", "deadline": overdue, "status": "pending"},
    )
    client.patch(
        f"/api/action-items/{items[1]['id']}",
        json={"owner_name": "产品经理", "deadline": due_today, "status": "in_progress"},
    )
    client.patch(
        f"/api/action-items/{items[2]['id']}",
        json={"owner_name": "测试同学", "deadline": future, "status": "pending"},
    )

    sent_meetings: list[tuple[int, list[int]]] = []

    def fake_send(meeting):
        sent_meetings.append((meeting.id, [item.id for item in meeting.action_items]))
        return "跟进提醒卡片已发送到飞书。"

    monkeypatch.setattr(follow_up_service, "send_follow_up_summary", fake_send)

    response = client.post("/api/follow-ups/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scanned_meetings"] == 1
    assert payload["total_candidates"] == 2
    assert payload["total_sent"] == 2
    assert len(payload["results"]) == 1
    assert payload["results"][0]["reminder_types"] == ["due_today", "overdue"]
    assert sent_meetings == [(created["id"], [items[0]["id"], items[1]["id"]])]


def test_run_follow_ups_returns_failed_when_delivery_fails(client, monkeypatch) -> None:
    import app.services.follow_up_service as follow_up_service

    today = utc_now().date().isoformat()

    created = client.post(
        "/api/meetings",
        json={
            "title": "失败提醒测试",
            "transcript": "Action: 后端同学排查日志",
        },
    ).json()

    item_id = created["action_items"][0]["id"]
    client.patch(
        f"/api/action-items/{item_id}",
        json={"owner_name": "后端同学", "deadline": today, "status": "pending"},
    )

    class FakeDeliveryError(Exception):
        pass

    monkeypatch.setattr(follow_up_service, "FeishuDeliveryError", FakeDeliveryError)

    def fake_send(_meeting):
        raise FakeDeliveryError("webhook unavailable")

    monkeypatch.setattr(follow_up_service, "send_follow_up_summary", fake_send)

    response = client.post("/api/follow-ups/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_candidates"] == 1
    assert payload["total_sent"] == 0
    assert payload["results"][0]["status"] == "failed"
    assert payload["results"][0]["message"] == "webhook unavailable"


def test_run_follow_ups_does_not_repeat_same_reminder_on_same_day(client, monkeypatch) -> None:
    import app.services.follow_up_service as follow_up_service

    today = utc_now().date().isoformat()

    created = client.post(
        "/api/meetings",
        json={
            "title": "重复提醒测试",
            "transcript": "Action: 前端同学更新活动页",
        },
    ).json()

    item_id = created["action_items"][0]["id"]
    client.patch(
        f"/api/action-items/{item_id}",
        json={"owner_name": "前端同学", "deadline": today, "status": "pending"},
    )

    sent_calls: list[int] = []

    def fake_send(meeting):
        sent_calls.append(meeting.id)
        return "跟进提醒卡片已发送到飞书。"

    monkeypatch.setattr(follow_up_service, "send_follow_up_summary", fake_send)

    first = client.post("/api/follow-ups/run")
    second = client.post("/api/follow-ups/run")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["total_sent"] == 1
    assert second.json()["total_sent"] == 0
    assert sent_calls == [created["id"]]


def test_should_run_auto_follow_up_only_once_per_day() -> None:
    from app.services.auto_follow_up_scheduler import should_run_auto_follow_up

    now = datetime(2026, 5, 29, 10, 0)

    assert should_run_auto_follow_up(now, None, 10, 0) is True
    assert should_run_auto_follow_up(now, now.date(), 10, 0) is False
    assert should_run_auto_follow_up(datetime(2026, 5, 29, 9, 59), None, 10, 0) is False


def test_classify_deadline_supports_relative_terms() -> None:
    from app.services.follow_up_service import _classify_deadline

    today = date(2026, 5, 29)  # Friday

    assert _classify_deadline("今天", today) == "due_today"
    assert _classify_deadline("明天", today) is None
    assert _classify_deadline("昨天", today) == "overdue"
    assert _classify_deadline("明天下午前", today) is None


def test_classify_deadline_supports_weekday_terms() -> None:
    from app.services.follow_up_service import _classify_deadline

    friday = date(2026, 5, 29)
    wednesday = date(2026, 5, 27)

    assert _classify_deadline("周五", friday) == "due_today"
    assert _classify_deadline("本周五下班前", friday) == "due_today"
    assert _classify_deadline("周三", friday) == "overdue"
    assert _classify_deadline("下周一", friday) is None
    assert _classify_deadline("周三", wednesday) == "due_today"


def test_classify_deadline_supports_absolute_chinese_dates() -> None:
    from app.services.follow_up_service import _classify_deadline

    today = date(2026, 5, 29)

    assert _classify_deadline("2026年5月29日", today) == "due_today"
    assert _classify_deadline("2026年5月28日", today) == "overdue"
