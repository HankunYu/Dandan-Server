import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from app.models.danmaku import DanmakuCache, TmdbCache
from app.models.file_match import FileMatch
from datetime import datetime, timedelta

async def show_cache_stats():
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
            # 获取弹幕缓存统计
            danmaku_count = await session.scalar(select(func.count()).select_from(DanmakuCache))
            danmaku_oldest = await session.scalar(
                select(func.min(DanmakuCache.created_at)).select_from(DanmakuCache)
            )
            danmaku_newest = await session.scalar(
                select(func.max(DanmakuCache.updated_at)).select_from(DanmakuCache)
            )
            
            # 获取TMDB缓存统计
            tmdb_count = await session.scalar(select(func.count()).select_from(TmdbCache))
            tmdb_oldest = await session.scalar(
                select(func.min(TmdbCache.created_at)).select_from(TmdbCache)
            )
            tmdb_newest = await session.scalar(
                select(func.max(TmdbCache.updated_at)).select_from(TmdbCache)
            )
            
            # 获取文件匹配记录统计
            file_match_count = await session.scalar(select(func.count()).select_from(FileMatch))
            file_match_oldest = await session.scalar(
                select(func.min(FileMatch.created_at)).select_from(FileMatch)
            )
            file_match_newest = await session.scalar(
                select(func.max(FileMatch.updated_at)).select_from(FileMatch)
            )
            
            # 打印统计信息
            print("\n=== 数据库缓存统计信息 ===")
            print("\n1. 弹幕缓存 (DanmakuCache):")
            print(f"   - 总记录数: {danmaku_count or 0}")
            if danmaku_oldest:
                print(f"   - 最早记录: {danmaku_oldest}")
            if danmaku_newest:
                print(f"   - 最新记录: {danmaku_newest}")
            
            print("\n2. TMDB缓存 (TmdbCache):")
            print(f"   - 总记录数: {tmdb_count or 0}")
            if tmdb_oldest:
                print(f"   - 最早记录: {tmdb_oldest}")
            if tmdb_newest:
                print(f"   - 最新记录: {tmdb_newest}")
            
            print("\n3. 文件匹配记录 (FileMatch):")
            print(f"   - 总记录数: {file_match_count or 0}")
            if file_match_oldest:
                print(f"   - 最早记录: {file_match_oldest}")
            if file_match_newest:
                print(f"   - 最新记录: {file_match_newest}")
            
            # 计算总缓存大小（估算）
            total_records = (danmaku_count or 0) + (tmdb_count or 0) + (file_match_count or 0)
            print(f"\n总缓存记录数: {total_records}")
            
        except Exception as e:
            print(f"获取统计信息时发生错误: {e}")
        finally:
            await session.close()
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(show_cache_stats()) 