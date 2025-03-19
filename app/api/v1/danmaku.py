from fastapi import APIRouter, Depends, HTTPException
from app.services.proxy import DanmakuProxy
from app.models.danmaku import MatchResponse
from app.models.requests import FileMatchRequest, SearchRequest
import os
from dotenv import load_dotenv
from typing import Dict, Any, List

# 加载环境变量
load_dotenv()

router = APIRouter()

@router.post("/match", response_model=MatchResponse)
async def match_file(request: FileMatchRequest) -> MatchResponse:
    print("Received request:", request.dict())
    proxy = DanmakuProxy()
    try:
        result = await proxy.match_file(
            file_name=request.file_name,
            file_hash=request.file_hash,
            file_size=request.file_size,  # 已经是整数
            video_duration=request.video_duration,  # 已经是浮点数
            match_mode=request.match_mode
        )
        print("Match result:", result)
        return result
    finally:
        await proxy.close()

@router.get("/{episode_id}")
async def get_danmaku(episode_id: int):
    proxy = DanmakuProxy()
    try:
        result = await proxy.get_danmaku(episode_id)
        return result
    finally:
        await proxy.close()

@router.post("/search")
async def search_anime(request: SearchRequest):
    proxy = DanmakuProxy()
    try:
        result = await proxy.search_anime(
            keyword=request.keyword,
            type=request.type,
            sub_group_id=request.sub_group_id,
            episode_id=request.episode_id,
            anime_id=request.anime_id,
            episode_number=request.episode_number,
            anime_type=request.anime_type,
            year=request.year,
            season=request.season,
            week=request.week,
            language=request.language,
            order=request.order,
            order_by=request.order_by,
            page=request.page,
            size=request.size
        )
        return result
    finally:
        await proxy.close() 