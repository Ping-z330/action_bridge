from collections.abc import Generator

# 数据库会话和模型基类的定义，使用 SQLAlchemy 来管理数据库连接和会话，以及定义数据库模型的基类；
# 同时配置了 SQLite 数据库的连接参数和一些性能优化的 PRAGMA 设置，以提高数据库的并发性能和稳定性。
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@event.listens_for(engine, "connect")
def configure_sqlite(connection, _record) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        # Fall back to default SQLite behavior if the database is already locked.
        pass
    finally:
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
