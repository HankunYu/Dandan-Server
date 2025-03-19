from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.danmaku import DanmakuCache
from ..config import settings

class DanmakuCacheManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_cached_danmaku(self, episode_id: int) -> Optional[Dict[str, Any]]:
        """
        从缓存中获取弹幕数据
        
        Args:
            episode_id: 节目编号
            
        Returns:
            Optional[Dict[str, Any]]: 缓存的弹幕数据
        """
        query = select(DanmakuCache).where(
            DanmakuCache.episode_id == episode_id,
            DanmakuCache.updated_at > datetime.now(UTC) - timedelta(minutes=settings.CACHE_EXPIRE_MINUTES)
        )
        result = await self.session.execute(query)
        cache = result.scalar_one_or_none()
        
        if cache:
            return cache.content
        return None

    async def cache_danmaku(self, episode_id: int, content: Dict[str, Any]) -> None:
        """
        缓存弹幕数据
        
        Args:
            episode_id: 节目编号
            content: 弹幕数据
        """
        cache = DanmakuCache(
            episode_id=episode_id,
            content=content
        )
        self.session.add(cache)
        await self.session.commit() 