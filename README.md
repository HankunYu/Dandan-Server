# Dandan Server

这是一个弹弹play API的代理服务器，提供弹幕数据的缓存和转发服务。

## 功能特点

- 支持弹幕数据的获取和缓存
- 支持文件识别和节目匹配
- 支持动画搜索
- 自动签名验证
- 异步处理请求
- SQLite数据库存储
- RESTful API接口

## 安装

1. 克隆项目
```bash
git clone https://github.com/yourusername/dandan-server.git
cd dandan-server
```

2. 创建虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
.\venv\Scripts\activate  # Windows
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的配置信息
```

## 运行

```bash
uvicorn app.main:app --reload
```

服务将在 http://localhost:8000 启动

## API文档

启动服务后访问 http://localhost:8000/docs 查看完整的API文档

## 主要API

### 获取弹幕

```
GET /api/v1/danmaku/{episode_id}
```

参数：
- episode_id: 节目编号

返回：
- 弹幕数据（JSON格式）

### 文件匹配

```
POST /api/v1/match
```

请求体：
```json
{
    "file_name": "string",
    "file_hash": "string",
    "file_size": 0,
    "video_duration": 0
}
```

参数说明：
- file_name: 视频文件名
- file_hash: 文件前16MB的MD5哈希值
- file_size: 文件大小（字节）
- video_duration: 视频时长（秒）

返回：
- 匹配结果列表（JSON格式）

### 搜索动画

```
POST /api/v1/search
```

请求体：
```json
{
    "keyword": "string"
}
```

参数说明：
- keyword: 搜索关键词

返回：
- 搜索结果列表（JSON格式）

## 开发

1. 安装开发依赖
```bash
pip install -r requirements-dev.txt
```

2. 运行测试
```bash
pytest
```

## 许可证

MIT 