from app.models.feishu_event_log import FeishuEventLog
from app.services.feishu_event_log_service import mark_feishu_event_finished, register_feishu_event


def test_register_feishu_event_returns_false_for_duplicate(db_session) -> None:
    assert register_feishu_event(db_session, "event-1", "meeting") is True
    assert register_feishu_event(db_session, "event-1", "meeting") is False

    logs = db_session.query(FeishuEventLog).all()
    assert len(logs) == 1
    assert logs[0].event_key == "event-1"
    assert logs[0].command_type == "meeting"


def test_mark_feishu_event_finished_updates_status(db_session) -> None:
    register_feishu_event(db_session, "event-2", "tasks")

    mark_feishu_event_finished(db_session, "event-2", "finished")

    log = db_session.query(FeishuEventLog).filter(FeishuEventLog.event_key == "event-2").one()
    assert log.status == "finished"
