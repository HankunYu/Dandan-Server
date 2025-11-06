from fastapi import APIRouter, Depends, HTTPException, Query
from app.services.proxy import DanmakuProxy
from app.models.danmaku import MatchResponse
from app.models.requests import FileMatchRequest, DanmakuWithDetailRequest, TmdbSearchRequest
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
import os
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
from app.models.search import AnimeType, AnimeSearchResponse

# 加载环境变量
load_dotenv()

router = APIRouter()

@router.post("/match", response_model=MatchResponse)
async def match_file(
    request: FileMatchRequest,
    db: AsyncSession = Depends(get_db)
) -> MatchResponse:
    proxy = DanmakuProxy(db)
    try:
        result = await proxy.match_file(
            file_name=request.file_name,
            file_hash=request.file_hash,
            file_size=request.file_size,
            video_duration=request.video_duration,
            match_mode=request.match_mode
        )
        return result
    finally:
        await proxy.close()

@router.get("/{episode_id}")
async def get_danmaku(
    episode_id: int,
    from_id: int = 0,
    with_related: bool = False,
    ch_convert: int = 0,
    cache_ttl: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    proxy = DanmakuProxy(db)
    try:
        result = await proxy.get_danmaku(
            episode_id=episode_id,
            from_id=from_id,
            with_related=with_related,
            ch_convert=ch_convert,
            cache_ttl=cache_ttl
        )
        return result
    finally:
        await proxy.close()

@router.post("/match_with_danmaku")
async def get_danmaku_with_detail(
    request: DanmakuWithDetailRequest,
    cache_ttl: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    通过文件信息匹配节目并获取弹幕数据
    
    Args:
        request: 包含文件信息和弹幕获取参数的请求
        cache_ttl: 缓存过期时间（分钟），如果为None则使用默认配置
        db: 数据库会话
        
    Returns:
        Dict[str, Any]: 弹幕数据，如果匹配失败则返回空字典
    """
    proxy = DanmakuProxy(db)
    try:
        result = await proxy.get_danmaku_with_detail(
            file_name=request.file_name,
            file_hash=request.file_hash,
            file_size=request.file_size,
            video_duration=request.video_duration,
            match_mode=request.match_mode,
            from_id=request.from_id,
            with_related=request.with_related,
            ch_convert=request.ch_convert,
            cache_ttl=cache_ttl
        )
        return result or {}
    finally:
        await proxy.close()

@router.post("/search/tmdb")
async def search_by_tmdb(
    request: TmdbSearchRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    通过TMDB ID搜索动画剧集
    
    Args:
        request: 包含TMDB ID和集数的请求
        db: 数据库会话
        
    Returns:
        Dict[str, Any]: 搜索结果，包含匹配的动画信息和剧集信息
    """
    proxy = DanmakuProxy(db)
    try:
        result = await proxy.search_by_tmdb(
            tmdb_id=request.tmdb_id,
            episode=request.episode
        )
        return result
    finally:
        await proxy.close()

@router.get("/search/anime", response_model=AnimeSearchResponse)
async def search_anime(
    keyword: str = Query(..., min_length=2, description="搜索关键词，至少两个字符"),
    anime_type: Optional[AnimeType] = Query(None, alias="type"),
    db: AsyncSession = Depends(get_db)
) -> AnimeSearchResponse:
    """
    根据关键词搜索作品
    """
    proxy = DanmakuProxy(db)
    try:
        result = await proxy.search_anime(
            keyword=keyword,
            anime_type=anime_type.value if anime_type else None
        )
        return AnimeSearchResponse(**result)
    finally:
        await proxy.close()
