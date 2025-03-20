from sqlalchemy import Column, Integer, String, DateTime, JSON
from datetime import datetime, UTC
from .base import Base

class ApiStats(Base):
    """API调用统计模型"""
    __tablename__ = "api_stats"

    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String(50), index=True)  # API端点名称
    method = Column(String(10))  # HTTP方法
    status_code = Column(Integer)  # 响应状态码
    response_time = Column(Integer)  # 响应时间（毫秒）
    timestamp = Column(DateTime, default=datetime.now(UTC))  # 调用时间
    params = Column(JSON, nullable=True)  # 请求参数
    error = Column(String(500), nullable=True)  # 错误信息（如果有） 