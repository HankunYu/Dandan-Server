from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class AnimeType(str, Enum):
    tvseries = "tvseries"
    tvspecial = "tvspecial"
    ova = "ova"
    movie = "movie"
    musicvideo = "musicvideo"
    web = "web"
    other = "other"
    jpmovie = "jpmovie"
    jpdrama = "jpdrama"
    unknown = "unknown"
    tmdbtv = "tmdbtv"
    tmdbmovie = "tmdbmovie"


class AnimeSearchItem(BaseModel):
    animeId: int
    animeTitle: Optional[str] = None
    bangumiId: Optional[str] = None
    episodeCount: int
    imageUrl: Optional[str] = None
    isFavorited: bool
    rating: Optional[float] = None
    startDate: Optional[str] = None
    type: AnimeType
    typeDescription: Optional[str] = None


class AnimeSearchResponse(BaseModel):
    success: bool = True
    errorCode: int = 0
    errorMessage: Optional[str] = None
    animes: Optional[List[AnimeSearchItem]] = None
