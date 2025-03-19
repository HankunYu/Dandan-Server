import hashlib
import base64
import time
from typing import Dict, Any
from ..config import settings

def generate_signature(path: str) -> tuple[str, str, str]:
    """
    生成弹弹play API所需的签名
    
    Args:
        path: API路径，例如 /api/v2/match
        
    Returns:
        tuple[str, str, str]: (签名, 时间戳, AppId)
    """
    # 获取时间戳
    timestamp = str(int(time.time()))
    
    # 获取AppId
    app_id = settings.DANDAN_APP_ID
    
    # 计算签名
    # base64(sha256(AppId + Timestamp + Path + AppSecret))
    sign_str = f"{app_id}{timestamp}{path}{settings.DANDAN_APP_SECRET}"
    sha256_hash = hashlib.sha256(sign_str.encode()).digest()
    signature = base64.b64encode(sha256_hash).decode()
    
    return signature, timestamp, app_id 