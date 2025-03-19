from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List
from ..database import get_db
from ..services.proxy import DanmakuProxy
from ..services.cache import DanmakuCacheManager
from ..models.requests import FileMatchRequest, SearchRequest

router = APIRouter()

@router.get("/danmaku/{episode_id}")
async def get_danmaku(
    episode_id: int,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取弹幕数据
    
    Args:
        episode_id: 节目编号
        db: 数据库会话
        
    Returns:
        Dict[str, Any]: 弹幕数据
    """
    # 检查缓存
    cache_manager = DanmakuCacheManager(db)
    cached_data = await cache_manager.get_cached_danmaku(episode_id)
    
    if cached_data:
        return cached_data
    
    # 从弹弹play获取数据
    proxy = DanmakuProxy()
    try:
        danmaku_data = await proxy.get_danmaku(episode_id)
        if not danmaku_data:
            raise HTTPException(status_code=404, detail="Danmaku not found")
            
        # 缓存数据
        await cache_manager.cache_danmaku(episode_id, danmaku_data)
        return danmaku_data
    finally:
        await proxy.close()

@router.post("/match")
async def match_file(
    request: FileMatchRequest,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    通过文件信息匹配节目
    
    Args:
        request: 文件匹配请求
        db: 数据库会话
        
    Returns:
        List[Dict[str, Any]]: 匹配结果列表
    """
    proxy = DanmakuProxy()
    try:
        matches = await proxy.match_file(
            file_name=request.file_name,
            file_hash=request.file_hash,
            file_size=request.file_size,
            video_duration=request.video_duration
        )
        if not matches:
            raise HTTPException(status_code=404, detail="No matches found")
        return matches
    finally:
        await proxy.close()

@router.post("/search")
async def search_anime(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    搜索动画
    
    Args:
        request: 搜索请求
        db: 数据库会话
        
    Returns:
        List[Dict[str, Any]]: 搜索结果列表
    """
    proxy = DanmakuProxy()
    try:
        results = await proxy.search_anime(request.keyword)
        if not results:
            raise HTTPException(status_code=404, detail="No results found")
        return results
    finally:
        await proxy.close() 