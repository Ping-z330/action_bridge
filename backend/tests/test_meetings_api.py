from sqlalchemy.exc import OperationalError


def test_create_meeting_and_fetch_detail(client) -> None:
    payload = {
        "title": "周会纪要",
        "transcript": "\n".join(
            [
                "讨论了本周上线风险和延期方案",
                "Decision: Beta 版本延期到周五",
                "Action: 前端更新落地页文案",
                "Next step: 产品经理确认用户通知时间",
            ]
        ),
    }

    create_response = client.post("/api/meetings", json=payload)

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["title"] == "周会纪要"
    assert created["summary"] == "讨论了本周上线风险和延期方案"
    assert len(created["action_items"]) == 2

    detail_response = client.get(f"/api/meetings/{created['id']}")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == created["id"]
    assert detail["decisions"] == ["Decision: Beta 版本延期到周五"]


def test_list_meetings_returns_created_records(client) -> None:
    client.post(
        "/api/meetings",
        json={
            "title": "需求评审会",
            "transcript": "讨论埋点方案\nDecision: 本周完成评审\nAction: 数据同学补充字段定义",
        },
    )

    response = client.get("/api/meetings")

    assert response.status_code == 200
    meetings = response.json()
    assert len(meetings) == 1
    assert meetings[0]["title"] == "需求评审会"


def test_create_meeting_returns_clear_message_when_database_is_locked(client, monkeypatch) -> None:
    import app.api.routes as routes

    def raise_locked_error(_db, _payload):
        raise OperationalError("insert", {}, Exception("database is locked"))

    monkeypatch.setattr(routes, "create_meeting_with_actions", raise_locked_error)

    response = client.post(
        "/api/meetings",
        json={
            "title": "锁冲突测试",
            "transcript": "Action: 测试数据库锁错误",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Database is temporarily locked. Please retry in a few seconds."


def test_send_feishu_returns_failed_when_webhook_missing(client, monkeypatch) -> None:
    import app.services.feishu_service as feishu_service

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "同步会",
            "transcript": "同步线上问题\nDecision: 明天修复\nAction: 后端定位日志",
        },
    )
    meeting_id = create_response.json()["id"]

    monkeypatch.setattr(feishu_service, "FEISHU_WEBHOOK_URL", None)

    response = client.post(f"/api/meetings/{meeting_id}/send-feishu")

    assert response.status_code == 200
    payload = response.json()
    assert payload["meeting_id"] == meeting_id
    assert payload["status"] == "failed"
    assert "FEISHU_WEBHOOK_URL" in payload["message"]


def test_send_feishu_returns_sent_when_webhook_succeeds(client, monkeypatch) -> None:
    import app.services.meeting_service as meeting_service

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "同步会",
            "transcript": "同步线上问题\nDecision: 明天修复\nAction: 后端定位日志",
        },
    )
    meeting_id = create_response.json()["id"]

    monkeypatch.setattr(meeting_service, "send_meeting_summary", lambda meeting: "会议摘要卡片已发送到飞书。")

    response = client.post(f"/api/meetings/{meeting_id}/send-feishu")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "sent"
    assert payload["message"] == "会议摘要卡片已发送到飞书。"


def test_send_follow_up_returns_sent_when_webhook_succeeds(client, monkeypatch) -> None:
    import app.services.meeting_service as meeting_service

    create_response = client.post(
        "/api/meetings",
        json={
            "title": "跟进会",
            "transcript": "Action: 前端更新落地页文案\nNext step: 产品经理确认上线时间",
        },
    )
    meeting_id = create_response.json()["id"]

    monkeypatch.setattr(meeting_service, "send_follow_up_summary", lambda meeting: "跟进提醒卡片已发送到飞书。")

    response = client.post(f"/api/meetings/{meeting_id}/follow-up")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "sent"
    assert payload["message"] == "跟进提醒卡片已发送到飞书。"


def test_send_follow_up_missing_meeting_returns_404(client) -> None:
    response = client.post("/api/meetings/9999/follow-up")

    assert response.status_code == 404


def test_patch_action_item_updates_owner_deadline_and_status(client) -> None:
    create_response = client.post(
        "/api/meetings",
        json={
            "title": "执行跟进会",
            "transcript": "Action: 前端更新落地页文案\nNext step: 产品经理确认上线时间",
        },
    )
    meeting = create_response.json()
    action_item_id = meeting["action_items"][0]["id"]

    response = client.patch(
        f"/api/action-items/{action_item_id}",
        json={
            "owner_name": "张三",
            "deadline": "周五下班前",
            "status": "in_progress",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    updated_item = next(item for item in payload["action_items"] if item["id"] == action_item_id)
    assert updated_item["owner_name"] == "张三"
    assert updated_item["deadline"] == "周五下班前"
    assert updated_item["status"] == "in_progress"


def test_patch_missing_action_item_returns_404(client) -> None:
    response = client.patch(
        "/api/action-items/9999",
        json={
            "owner_name": "张三",
            "deadline": "周五下班前",
            "status": "completed",
        },
    )

    assert response.status_code == 404


def test_get_missing_meeting_returns_404(client) -> None:
    response = client.get("/api/meetings/9999")

    assert response.status_code == 404
