from sqlalchemy import inspect, text

from app.db.session import engine


def run_lightweight_migrations() -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    with engine.begin() as connection:
        if "feishu_event_logs" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE feishu_event_logs (
                        id INTEGER NOT NULL PRIMARY KEY,
                        event_key VARCHAR(128) NOT NULL UNIQUE,
                        command_type VARCHAR(32) DEFAULT 'unknown' NOT NULL,
                        status VARCHAR(32) DEFAULT 'processing' NOT NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_feishu_event_logs_id ON feishu_event_logs (id)"))
            connection.execute(text("CREATE UNIQUE INDEX ix_feishu_event_logs_event_key ON feishu_event_logs (event_key)"))

        if "memory_aliases" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE memory_aliases (
                        id INTEGER NOT NULL PRIMARY KEY,
                        alias VARCHAR(120) NOT NULL UNIQUE,
                        target VARCHAR(255) NOT NULL,
                        memory_type VARCHAR(32) DEFAULT 'alias' NOT NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_memory_aliases_id ON memory_aliases (id)"))
            connection.execute(text("CREATE UNIQUE INDEX ix_memory_aliases_alias ON memory_aliases (alias)"))

        if "pending_agent_actions" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE pending_agent_actions (
                        id INTEGER NOT NULL PRIMARY KEY,
                        chat_id VARCHAR(128) NOT NULL,
                        action_type VARCHAR(64) NOT NULL,
                        payload_json TEXT NOT NULL,
                        status VARCHAR(32) DEFAULT 'pending' NOT NULL,
                        created_at DATETIME NOT NULL,
                        expires_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_pending_agent_actions_id ON pending_agent_actions (id)"))
            connection.execute(text("CREATE INDEX ix_pending_agent_actions_chat_id ON pending_agent_actions (chat_id)"))

        if "agent_task_contexts" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE agent_task_contexts (
                        id INTEGER NOT NULL PRIMARY KEY,
                        chat_id VARCHAR(128) NOT NULL UNIQUE,
                        item_ids_json TEXT NOT NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_agent_task_contexts_id ON agent_task_contexts (id)"))
            connection.execute(text("CREATE UNIQUE INDEX ix_agent_task_contexts_chat_id ON agent_task_contexts (chat_id)"))

    if "action_items" not in table_names:
        return

    existing_columns = {column["name"] for column in inspector.get_columns("action_items")}
    with engine.begin() as connection:
        if "deadline_date" not in existing_columns:
            connection.execute(text("ALTER TABLE action_items ADD COLUMN deadline_date VARCHAR(10) DEFAULT ''"))
        if "deadline_time" not in existing_columns:
            connection.execute(text("ALTER TABLE action_items ADD COLUMN deadline_time VARCHAR(5) DEFAULT ''"))
