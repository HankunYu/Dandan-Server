from sqlalchemy import Column, Integer, String, JSON, DateTime
from datetime import datetime, UTC
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from .base import Base

class Danmaku(Base):
    __tablename__ = "danmaku"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, index=True)
    content = Column(JSON)
    created_at = Column(DateTime, default=datetime.now(UTC))
    updated_at = Column(DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC))

class DanmakuCache(Base):
    __tablename__ = "danmaku_cache"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, index=True)
    content = Column(JSON)
    created_at = Column(DateTime, default=datetime.now(UTC))
    updated_at = Column(DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC))

class MatchItem(BaseModel):
    episodeId: int
    animeId: int
    animeTitle: str
    episodeTitle: str
    type: str
    typeDescription: str
    shift: int = 0

class MatchResponse(BaseModel):
    errorCode: int = 0
    success: bool = True
    errorMessage: str = ""
    isMatched: bool = False
    matches: List[MatchItem] = []
