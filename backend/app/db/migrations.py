from sqlalchemy import inspect, text

from app.db.session import engine


def run_lightweight_migrations() -> None:
    # 轻量级迁移入口：启动时检查缺失的表/字段，并用 SQL 补齐。
    # 这个项目没有使用 Alembic，所以这里承担了“简单数据库升级”的职责。
    inspector = inspect(engine)
    # 先读取当前数据库里已有的表名，后面按需创建缺失的表。
    table_names = inspector.get_table_names()

    with engine.begin() as connection:
        if "feishu_event_logs" not in table_names:
            # 飞书事件日志表：用于事件去重，避免同一个飞书事件被重复处理。
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
            # 记忆别名表：保存用户定义的“简称 -> 正式名称”映射。
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
            # 待确认 Agent 动作表：保存“创建任务/改负责人/改截止时间”等需要用户确认的操作。
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
            # Agent 任务上下文表：保存最近展示给某个会话的任务 ID 列表。
            # 这样用户说“第二个任务”时，系统能知道指的是哪一个。
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

        if "agent_trace_logs" not in table_names:
            # Agent 调试轨迹表：记录消息、识别意图、调用工具、回复等过程。
            connection.execute(
                text(
                    """
                    CREATE TABLE agent_trace_logs (
                        id INTEGER NOT NULL PRIMARY KEY,
                        chat_id VARCHAR(128) DEFAULT '' NOT NULL,
                        source VARCHAR(32) DEFAULT 'agent' NOT NULL,
                        message TEXT DEFAULT '' NOT NULL,
                        normalized_message TEXT DEFAULT '' NOT NULL,
                        intent_name VARCHAR(64) DEFAULT 'unhandled' NOT NULL,
                        intent_filters_json TEXT DEFAULT '{}' NOT NULL,
                        tool_name VARCHAR(64) DEFAULT '' NOT NULL,
                        tool_source VARCHAR(32) DEFAULT '' NOT NULL,
                        tool_category VARCHAR(64) DEFAULT '' NOT NULL,
                        tool_executed BOOLEAN DEFAULT 0 NOT NULL,
                        dangerous BOOLEAN DEFAULT 0 NOT NULL,
                        requires_confirmation BOOLEAN DEFAULT 0 NOT NULL,
                        response_message TEXT DEFAULT '' NOT NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_agent_trace_logs_id ON agent_trace_logs (id)"))

        if "project_channels" not in table_names:
            # 项目群绑定表：保存项目关键词和飞书群 receive_id 的绑定关系。
            connection.execute(
                text(
                    """
                    CREATE TABLE project_channels (
                        id INTEGER NOT NULL PRIMARY KEY,
                        project_keyword VARCHAR(120) NOT NULL UNIQUE,
                        receive_id VARCHAR(128) NOT NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_project_channels_id ON project_channels (id)"))
            connection.execute(text("CREATE UNIQUE INDEX ix_project_channels_project_keyword ON project_channels (project_keyword)"))
            connection.execute(text("CREATE INDEX ix_project_channels_receive_id ON project_channels (receive_id)"))

    # action_items 是旧表；如果数据库还没有这张表，后面的字段补丁就不执行。
    if "action_items" not in table_names:
        return

    # 给旧版 action_items 表补充 deadline_date / deadline_time 字段。
    existing_columns = {column["name"] for column in inspector.get_columns("action_items")}
    with engine.begin() as connection:
        if "deadline_date" not in existing_columns:
            # deadline_date 用来保存规范化后的日期，便于判断今天到期/逾期。
            connection.execute(text("ALTER TABLE action_items ADD COLUMN deadline_date VARCHAR(10) DEFAULT ''"))
        if "deadline_time" not in existing_columns:
            # deadline_time 用来保存规范化后的时间，便于后续更细粒度提醒。
            connection.execute(text("ALTER TABLE action_items ADD COLUMN deadline_time VARCHAR(5) DEFAULT ''"))
