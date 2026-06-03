from app.agent.schemas import AgentIntent


CONFIRMED_INTENT_BY_ACTION_TYPE = {
    "create_task": "confirm_create_task",
    "update_task_deadline": "confirm_update_task_deadline",
    "update_task_owner": "confirm_update_task_owner",
}


def build_confirmed_action_intent(
    action_type: str | None,
    payload: dict[str, str] | None,
) -> AgentIntent | None:
    if not action_type or not payload:
        return None

    intent_name = CONFIRMED_INTENT_BY_ACTION_TYPE.get(action_type)
    if not intent_name:
        return None

    return AgentIntent(name=intent_name, filters=payload)
