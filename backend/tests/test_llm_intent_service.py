from app.agent.llm_intent_service import _intent_from_payload


def test_intent_from_payload_accepts_valid_owner_update() -> None:
    intent = _intent_from_payload(
        {
            "intent": "update_task_owner",
            "filters": {
                "action_item_id": "12",
                "owner_name": "测试同学",
            },
        }
    )

    assert intent is not None
    assert intent.name == "update_task_owner"
    assert intent.filters == {"action_item_id": "12", "owner_name": "测试同学"}


def test_intent_from_payload_rejects_update_without_task_id() -> None:
    intent = _intent_from_payload(
        {
            "intent": "update_task_owner",
            "filters": {"owner_name": "测试同学"},
        }
    )

    assert intent is None


def test_intent_from_payload_rejects_invalid_status() -> None:
    intent = _intent_from_payload(
        {
            "intent": "update_task_status",
            "filters": {
                "action_item_id": "12",
                "status": "deleted",
            },
        }
    )

    assert intent is None


def test_intent_from_payload_defaults_query_to_open_tasks() -> None:
    intent = _intent_from_payload({"intent": "query_tasks", "filters": {}})

    assert intent is not None
    assert intent.name == "query_tasks"
    assert intent.filters == {"open_only": "true"}
