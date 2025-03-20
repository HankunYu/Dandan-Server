import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import delete
from app.models.danmaku import DanmakuCache, TmdbCache
from app.models.file_match import FileMatch

async def clear_cache():
    # 创建数据库引擎
    engine = create_async_engine(
        "sqlite+aiosqlite:///./dandan.db",
        echo=True
    )
    
    # 创建会话工厂
    async_session = async_sessionmaker(
        engine,
        expire_on_commit=False
    )
    
    # 创建会话
    async with async_session() as session:
        try:
            # 删除所有缓存数据
            await session.execute(delete(DanmakuCache))
            await session.execute(delete(TmdbCache))
            await session.execute(delete(FileMatch))
            
            await session.commit()
            print("所有缓存数据已成功清除！")
            
        except Exception as e:
            print(f"清除缓存时发生错误: {e}")
            await session.rollback()
        finally:
            await session.close()
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(clear_cache()) 