from fastapi import APIRouter, Depends, HTTPException
from app.services.proxy import DanmakuProxy
from app.models.danmaku import MatchResponse
from app.models.requests import FileMatchRequest, DanmakuWithDetailRequest
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
import os
from dotenv import load_dotenv
from typing import Dict, Any, List

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
    db: AsyncSession = Depends(get_db)
):
    proxy = DanmakuProxy(db)
    try:
        result = await proxy.get_danmaku(
            episode_id=episode_id,
            from_id=from_id,
            with_related=with_related,
            ch_convert=ch_convert
        )
        return result
    finally:
        await proxy.close()

@router.post("/match_with_danmaku")
async def get_danmaku_with_detail(
    request: DanmakuWithDetailRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    通过文件信息匹配节目并获取弹幕数据
    
    Args:
        request: 包含文件信息和弹幕获取参数的请求
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
            ch_convert=request.ch_convert
        )
        return result or {}
    finally:
        await proxy.close() 