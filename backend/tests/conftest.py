from collections.abc import Generator
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.main import app
from app.models.action_item import ActionItem
from app.models.follow_up_log import FollowUpLog
from app.models.meeting import Meeting
from app.models.task import Task


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    db = SessionLocal()
    try:
        db.query(FollowUpLog).delete()
        db.query(ActionItem).delete()
        db.query(Task).delete()
        db.query(Meeting).delete()
        db.commit()
        yield
    finally:
        db.query(FollowUpLog).delete()
        db.query(ActionItem).delete()
        db.query(Task).delete()
        db.query(Meeting).delete()
        db.commit()
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
