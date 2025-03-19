from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import danmaku
from .database import init_db

app = FastAPI(
    title="Dandan Server",
    description="A proxy server for Dandanplay API",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(danmaku.router, prefix="/api/v1", tags=["danmaku"])

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    await init_db() 