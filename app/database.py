import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .config import settings
from .models.danmaku import Base as DanmakuBase
from .models.file_match import Base as FileMatchBase

# 确保数据库目录存在
db_dir = os.path.dirname(settings.DATABASE_URL.replace('sqlite+aiosqlite:///', ''))
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir)

# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    future=True
)

# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    """初始化数据库"""
    async with engine.begin() as conn:
        # 创建所有表
        await conn.run_sync(DanmakuBase.metadata.create_all)
        await conn.run_sync(FileMatchBase.metadata.create_all)

async def get_db():
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close() 