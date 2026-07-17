from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.db.base import Base
from app.db.migrations import run_lightweight_migrations
from app.db.session import engine
from app.services.auto_follow_up_scheduler import AutoFollowUpScheduler

# 启动时根据 ORM 模型创建数据库表。
# 如果表已经存在，SQLAlchemy 不会重复创建。
Base.metadata.create_all(bind=engine)

# 执行轻量级迁移：补齐历史版本缺少的表或字段。
run_lightweight_migrations()

# 自动跟进调度器：应用启动后按配置时间扫描到期/逾期任务。
scheduler = AutoFollowUpScheduler()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # FastAPI 生命周期钩子：应用启动时开启后台调度器。
    await scheduler.start()
    try:
        yield
    finally:
        # 应用关闭时停止后台调度器，避免后台任务悬挂。
        await scheduler.stop()


# 创建 FastAPI 应用实例，并把 lifespan 绑定进去。
app = FastAPI(title="ActionBridge API", version="0.1.0", lifespan=lifespan)

# CORS 配置：允许前端页面跨域访问后端 API。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 agent-debug 安全中间件（生产环境禁用或需要 API Key）。
from app.core.security import agent_debug_middleware
app.middleware("http")(agent_debug_middleware)

# 注册所有业务 API 路由。
app.include_router(router)

# 注册 Demo API（A2A 多 Agent 协作模拟）。
from app.api.demo_routes import demo_router
app.include_router(demo_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    # 健康检查接口，用来确认后端服务是否启动成功。
    return {"status": "ok"}
