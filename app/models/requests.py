from pydantic import BaseModel, Field
from typing import Optional

class FileMatchRequest(BaseModel):
    file_name: str
    file_hash: str
    file_size: int
    video_duration: int
    match_mode: Optional[str] = "hashAndFileName"

    class Config:
        json_schema_extra = {
            "example": {
                "file_name": "葬送的芙莉莲 - S01E01.mkv",
                "file_hash": "0a27428e49e9d6fddee74fcafb888027",
                "file_size": 0,
                "video_duration": 0,
                "match_mode": "hashAndFileName"
            }
        }

    def dict(self, *args, **kwargs):
        d = super().dict(*args, **kwargs)
        # 确保数值类型正确
        d['file_size'] = int(d['file_size'])
        d['video_duration'] = int(d['video_duration'])
        return d

class DanmakuWithDetailRequest(FileMatchRequest):
    """包含弹幕获取参数的请求模型"""
    from_id: Optional[int] = 0
    with_related: Optional[bool] = True
    ch_convert: Optional[int] = 0

    class Config:
        json_schema_extra = {
            "example": {
                "file_name": "葬送的芙莉莲 - S01E01.mkv",
                "file_hash": "0a27428e49e9d6fddee74fcafb888027",
                "file_size": 0,
                "video_duration": 0,
                "match_mode": "hashAndFileName",
                "from_id": 0,
                "with_related": True,
                "ch_convert": 0
            }
        }

class TmdbSearchRequest(BaseModel):
    """TMDB ID搜索请求模型"""
    tmdb_id: int
    # 省略集数表示整季查询：返回该作品在弹弹play的全部条目及完整剧集列表，
    # 客户端可据此在本地完成集号映射，无需逐集回源。
    # 限定非负，使内部的整季哨兵值（SERIES_EPISODE）从外部不可达
    episode: Optional[int] = Field(None, ge=0)
    # tmdbId类型：0=电视剧（默认），1=电影，与弹弹play上游的tmdbIdType参数一致
    tmdb_id_type: Optional[int] = 0

    class Config:
        json_schema_extra = {
            "example": {
                "tmdb_id": 100049,
                "episode": 2,
                "tmdb_id_type": 0
            }
        }