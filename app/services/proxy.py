import httpx
from typing import Dict, Any, Optional, List
from ..config import settings
from .signature import generate_signature
from fastapi import HTTPException
from app.models.danmaku import MatchResponse

class DanmakuProxy:
    def __init__(self):
        self.base_url = settings.DANDAN_API_BASE_URL
        self.client = httpx.AsyncClient()

    async def get_danmaku(
        self,
        episode_id: int,
        from_id: int = 0,
        with_related: bool = True,
        ch_convert: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        从弹弹play获取弹幕数据
        
        Args:
            episode_id: 节目编号
            from_id: 起始弹幕编号，忽略此编号以前的弹幕
            with_related: 是否同时获取关联的第三方弹幕
            ch_convert: 中文简繁转换。0-不转换，1-转换为简体，2-转换为繁体
            
        Returns:
            Optional[Dict[str, Any]]: 弹幕数据
        """
        path = f"/api/v2/comment/{episode_id}"
        signature, timestamp, app_id = generate_signature(path)
        
        headers = {
            'X-AppId': app_id,
            'X-Timestamp': timestamp,
            'X-Signature': signature
        }
        
        params = {
            'from': from_id,
            'withRelated': str(with_related).lower(),
            'chConvert': ch_convert
        }
        
        try:
            response = await self.client.get(
                f"{self.base_url}{path}",
                params=params,
                headers=headers,
                follow_redirects=True  # 允许自动跟随重定向
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(f"Error fetching danmaku: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def match_file(
        self,
        file_name: str,
        file_hash: str,
        file_size: int,
        video_duration: int,
        match_mode: str = "hashAndFileName"
    ) -> MatchResponse:
        """
        通过文件信息匹配节目
        
        Args:
            file_name: 文件名
            file_hash: 文件前16MB的MD5哈希值
            file_size: 文件大小（字节）
            video_duration: 视频时长（秒）
            match_mode: 匹配模式（hashAndFileName: 文件名和哈希值匹配）
            
        Returns:
            MatchResponse: 匹配结果
        """
        path = "/api/v2/match"
        signature, timestamp, app_id = generate_signature(path)
        
        data = {
            'fileName': file_name,
            'fileHash': file_hash,
            'fileSize': file_size,
            'videoDuration': video_duration,
            'matchMode': match_mode
        }
        
        headers = {
            'X-AppId': app_id,
            'X-Timestamp': timestamp,
            'X-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        print("Request URL:", f"{self.base_url}{path}")
        print("Request Headers:", headers)
        print("Request Data:", data)
        
        try:
            response = await self.client.post(
                f"{self.base_url}{path}",
                json=data,
                headers=headers
            )
            print("Response Status:", response.status_code)
            print("Response Headers:", dict(response.headers))
            response.raise_for_status()
            result = response.json()
            print("Response Body:", result)
            if not isinstance(result, dict):
                raise ValueError("Invalid response format")
            
            # 确保 matches 字段是列表类型
            if result.get('matches') is None:
                result['matches'] = []
                
            return MatchResponse(**result)
            
        except Exception as e:
            print(f"Error matching file: {e}")
            return MatchResponse(
                errorCode=500,
                success=False,
                errorMessage=str(e),
                isMatched=False,
                matches=[]
            )

    async def search_anime(self, keyword: str) -> Optional[List[Dict[str, Any]]]:
        """
        搜索动画
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            Optional[List[Dict[str, Any]]]: 搜索结果列表
        """
        path = "/api/v2/search"
        signature, timestamp, app_id = generate_signature(path)
        
        data = {
            'keyword': keyword
        }
        
        headers = {
            'X-AppId': app_id,
            'X-Timestamp': timestamp,
            'X-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        try:
            response = await self.client.post(
                f"{self.base_url}{path}",
                json=data,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(f"Error searching anime: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose() 