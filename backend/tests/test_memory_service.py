from app.services.memory_service import (
    forget_alias,
    list_memory_aliases,
    normalize_message_with_memory,
    remember_alias,
)


def test_remember_alias_creates_and_updates_memory(db_session) -> None:
    created = remember_alias(db_session, "官网", "官网改版", "project")

    assert created.alias == "官网"
    assert created.target == "官网改版"
    assert created.memory_type == "project"

    updated = remember_alias(db_session, "官网", "官网改版上线", "project")

    assert updated.id == created.id
    assert updated.target == "官网改版上线"
    assert len(list_memory_aliases(db_session)) == 1


def test_normalize_message_with_memory_replaces_aliases(db_session) -> None:
    remember_alias(db_session, "官网", "官网改版", "project")
    remember_alias(db_session, "张三", "前端同学", "user")

    normalized = normalize_message_with_memory(db_session, "官网进度怎么样，张三还有什么任务")

    assert normalized == "官网改版进度怎么样，前端同学还有什么任务"


def test_forget_alias_deletes_memory(db_session) -> None:
    remember_alias(db_session, "官网", "官网改版", "project")

    deleted = forget_alias(db_session, "官网")

    assert deleted is not None
    assert deleted.alias == "官网"
    assert list_memory_aliases(db_session) == []

