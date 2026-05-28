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


def test_send_feishu_returns_placeholder_message(client) -> None:
    create_response = client.post(
        "/api/meetings",
        json={
            "title": "同步会",
            "transcript": "同步线上问题\nDecision: 明天修复\nAction: 后端定位日志",
        },
    )
    meeting_id = create_response.json()["id"]

    response = client.post(f"/api/meetings/{meeting_id}/send-feishu")

    assert response.status_code == 200
    payload = response.json()
    assert payload["meeting_id"] == meeting_id
    assert payload["status"] == "queued"


def test_get_missing_meeting_returns_404(client) -> None:
    response = client.get("/api/meetings/9999")

    assert response.status_code == 404
