from sqlalchemy import Column, Integer, String, JSON, DateTime, UniqueConstraint
from sqlalchemy.sql import func
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
    """弹幕数据缓存模型"""
    __tablename__ = "danmaku_cache"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, index=True, nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class MatchItem(BaseModel):
    episodeId: int
    animeId: int
    animeTitle: str
    episodeTitle: str
    type: str
    typeDescription: str
    shift: int = 0

class MatchResponse(BaseModel):
    errorCode: Optional[int] = None
    success: bool = True
    errorMessage: Optional[str] = None
    isMatched: bool = False
    matches: List[Dict[str, Any]] = []

class TmdbCache(Base):
    """TMDB搜索结果缓存模型"""
    __tablename__ = "tmdb_cache"

    id = Column(Integer, primary_key=True, index=True)
    tmdb_id = Column(Integer, index=True, nullable=False)
    episode = Column(Integer, nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('tmdb_id', 'episode', name='uix_tmdb_episode'),
    )
