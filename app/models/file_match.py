from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from datetime import datetime, UTC
from .base import Base

class FileMatch(Base):
    __tablename__ = "file_matches"

    id = Column(Integer, primary_key=True, index=True)
    file_hash = Column(String(32), index=True)
    episode_id = Column(Integer, index=True)
    file_name = Column(String(255))
    file_size = Column(Integer)
    video_duration = Column(Integer)
    created_at = Column(DateTime, default=datetime.now(UTC))
    updated_at = Column(DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC))

    # 添加唯一约束，确保同一个hash不会重复添加
    __table_args__ = (
        UniqueConstraint('file_hash', name='uix_file_hash'),
    ) 