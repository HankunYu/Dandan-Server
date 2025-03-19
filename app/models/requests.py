from pydantic import BaseModel
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

class SearchRequest(BaseModel):
    keyword: str 