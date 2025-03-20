import logging
import logging.handlers
import os
from pathlib import Path

def setup_logger():
    """
    配置日志系统
    """
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # 文件处理器 - 按日期轮转
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "app.log",
        when="midnight",
        interval=1,
        backupCount=30,  # 保留30天的日志
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # 错误日志处理器 - 单独记录错误日志
    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "error.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # 添加处理器到根日志记录器
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    
    # 设置第三方库的日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING) 