import asyncio
import os
from dotenv import load_dotenv
from app.services.proxy import DanmakuProxy
from app.database import init_db

# 加载环境变量
load_dotenv()

async def test_match():
    # 初始化数据库
    await init_db()
    
    proxy = DanmakuProxy()
    try:
        # 测试数据
        test_data = {
            "file_name": "名侦探柯南：漆黑的追踪者 (2009) - 1080p.mkv",
            "file_hash": "ef6980845c92654477c935edc5c0d6f4",
            "file_size": 0,
            "video_duration": 0
        }
        
        result = await proxy.match_file(**test_data)
        print("Match result:", result)
    finally:
        await proxy.close()

if __name__ == "__main__":
    asyncio.run(test_match()) 