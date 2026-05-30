from sqlalchemy import inspect, text

from app.db.session import engine


def run_lightweight_migrations() -> None:
    inspector = inspect(engine)
    if "action_items" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("action_items")}
    with engine.begin() as connection:
        if "deadline_date" not in existing_columns:
            connection.execute(text("ALTER TABLE action_items ADD COLUMN deadline_date VARCHAR(10) DEFAULT ''"))
        if "deadline_time" not in existing_columns:
            connection.execute(text("ALTER TABLE action_items ADD COLUMN deadline_time VARCHAR(5) DEFAULT ''"))
