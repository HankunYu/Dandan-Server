from urllib.parse import quote

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import JSONResponse
from .api.v1 import danmaku, stats
from .api.v1.stats import verify_token
from .database import init_db
from .services import upstream
from .services.stats_retention import start_retention_worker, stop_retention_worker
from app.utils.logger import setup_logger
import logging
from app.middleware.api_stats import ApiStatsMiddleware

# 初始化日志配置
setup_logger()
logger = logging.getLogger(__name__)

# 关闭自动生成的文档路由，下方以token保护的方式重新提供
app = FastAPI(
    title="Dandan Server",
    description="A proxy server for Dandanplay API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/openapi.json", include_in_schema=False)
async def openapi_json(token: str = Query("")) -> JSONResponse:
    verify_token(token)
    return JSONResponse(app.openapi())


@app.get("/docs", include_in_schema=False)
async def swagger_docs(token: str = Query("")):
    verify_token(token)
    return get_swagger_ui_html(
        openapi_url=f"/openapi.json?token={quote(token)}",
        title="Dandan Server - Docs",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_docs(token: str = Query("")):
    verify_token(token)
    return get_redoc_html(
        openapi_url=f"/openapi.json?token={quote(token)}",
        title="Dandan Server - ReDoc",
    )

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ApiStatsMiddleware)

# 注册路由
app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
app.include_router(danmaku.router, prefix="/api/v1", tags=["danmaku"])

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库和后台刷新任务"""
    await init_db()
    upstream.start_refresh_worker()
    start_retention_worker()
    logger.info("应用程序启动")

@app.on_event("shutdown")
async def shutdown_event():
    await stop_retention_worker()
    await upstream.stop_refresh_worker()
    await upstream.close_client()
    logger.info("应用程序关闭") 