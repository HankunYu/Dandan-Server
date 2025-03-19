from pydantic import BaseModel
from typing import Optional

class FileMatchRequest(BaseModel):
    file_name: str
    file_hash: str
    file_size: int
    video_duration: float
    match_mode: Optional[int] = 1

class SearchRequest(BaseModel):
    keyword: str 