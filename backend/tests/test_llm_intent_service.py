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


def test_intent_from_payload_asks_reference_without_task_id() -> None:
    intent = _intent_from_payload(
        {
            "intent": "update_task_owner",
            "filters": {"owner_name": "测试同学"},
        }
    )

    assert intent is not None
    assert intent.name == "clarify_task_reference"
    assert intent.filters["missing_fields"] == "任务编号"


def test_intent_from_payload_asks_reference_when_llm_invents_task_id() -> None:
    intent = _intent_from_payload(
        {
            "intent": "update_task_owner",
            "filters": {
                "action_item_id": "12",
                "owner_name": "测试同学",
            },
        },
        source_message="那个任务改成测试同学负责",
    )

    assert intent is not None
    assert intent.name == "clarify_task_reference"
    assert intent.filters["missing_fields"] == "任务编号"


def test_intent_from_payload_preserves_update_slots_when_task_id_is_missing() -> None:
    intent = _intent_from_payload(
        {
            "intent": "update_task_owner",
            "filters": {
                "owner_name": "QA",
            },
        },
        source_message="把 login page 那个任务交给 QA",
    )

    assert intent is not None
    assert intent.name == "clarify_task_reference"
    assert intent.filters["target_intent"] == "update_task_owner"
    assert intent.filters["owner_name"] == "QA"


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
