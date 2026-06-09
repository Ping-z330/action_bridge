from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import DATABASE_URL

# 创建数据库引擎。engine 可以理解成 SQLAlchemy 连接数据库的“入口”。
engine = create_engine(
    DATABASE_URL,
    # SQLite 默认不允许跨线程使用同一个连接；FastAPI 场景下需要关掉这个限制。
    # timeout=30 表示数据库被占用时最多等待 30 秒，减少“database is locked”的概率。
    connect_args={"check_same_thread": False, "timeout": 30},
)

# SessionLocal 是数据库会话工厂；每次请求通常会创建一个新的 Session。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base 是所有 SQLAlchemy ORM 模型的基类，模型类会继承它来映射数据库表。
Base = declarative_base()


@event.listens_for(engine, "connect")
def configure_sqlite(connection, _record) -> None:
    # 每次 SQLite 连接建立时，设置一些 PRAGMA 参数来提升稳定性和并发能力。
    cursor = connection.cursor()
    try:
        # busy_timeout：数据库被锁时等待一段时间，而不是立刻报错。
        cursor.execute("PRAGMA busy_timeout=30000;")
        # WAL 模式可以提升 SQLite 读写并发能力。
        cursor.execute("PRAGMA journal_mode=WAL;")
        # NORMAL 在性能和数据安全之间做折中，适合这个轻量项目。
        cursor.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        # Fall back to default SQLite behavior if the database is already locked.
        pass
    finally:
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    # FastAPI 依赖函数：接口里 Depends(get_db) 时，会拿到这里创建的 db 会话。
    db = SessionLocal()
    try:
        # yield 把 db 交给接口使用；接口执行完后会继续执行 finally。
        yield db
    finally:
        # 请求结束后关闭会话，避免连接泄漏。
        db.close()
