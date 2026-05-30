def test_feishu_card_callback_marks_action_item_completed(client) -> None:
    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Feishu callback review",
            "transcript": "\n".join(
                [
                    "Discussed card callback.",
                    "Decision: support completion callback",
                    "Action: backend update action status",
                ]
            ),
        },
    )
    meeting = create_response.json()
    action_item_id = meeting["action_items"][0]["id"]

    response = client.post(
        "/api/feishu/card-callback",
        json={
            "action": {
                "value": {
                    "action": "complete_action_item",
                    "action_item_id": action_item_id,
                }
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "行动项已标记为完成。",
        "action_item_id": action_item_id,
    }

    detail_response = client.get(f"/api/meetings/{meeting['id']}")
    updated_item = detail_response.json()["action_items"][0]
    assert updated_item["status"] == "completed"


def test_feishu_card_callback_rejects_unknown_action(client) -> None:
    response = client.post(
        "/api/feishu/card-callback",
        json={
            "action": {
                "value": {
                    "action": "unknown",
                    "action_item_id": 1,
                }
            }
        },
    )

    assert response.status_code == 400
