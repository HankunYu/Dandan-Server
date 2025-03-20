from fastapi import APIRouter, Depends, HTTPException
from app.services.proxy import DanmakuProxy
from app.models.danmaku import MatchResponse
from app.models.requests import FileMatchRequest
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