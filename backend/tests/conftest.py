from collections.abc import Generator
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.main import app
from app.models.action_item import ActionItem
from app.models.agent_task_context import AgentTaskContext
from app.models.feishu_event_log import FeishuEventLog
from app.models.follow_up_log import FollowUpLog
from app.models.memory_alias import MemoryAlias
from app.models.meeting import Meeting
from app.models.pending_agent_action import PendingAgentAction
from app.models.task import Task


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch) -> None:
    import app.services.parser_service as parser_service

    monkeypatch.setattr(parser_service, "PARSER_PROVIDER", "rules")


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    db = SessionLocal()
    try:
        db.query(FollowUpLog).delete()
        db.query(FeishuEventLog).delete()
        db.query(PendingAgentAction).delete()
        db.query(MemoryAlias).delete()
        db.query(AgentTaskContext).delete()
        db.query(ActionItem).delete()
        db.query(Task).delete()
        db.query(Meeting).delete()
        db.commit()
        yield
    finally:
        db.query(FollowUpLog).delete()
        db.query(FeishuEventLog).delete()
        db.query(PendingAgentAction).delete()
        db.query(MemoryAlias).delete()
        db.query(AgentTaskContext).delete()
        db.query(ActionItem).delete()
        db.query(Task).delete()
        db.query(Meeting).delete()
        db.commit()
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
