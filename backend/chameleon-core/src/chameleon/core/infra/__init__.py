"""运行时基础设施（启动期初始化、跨层共享）

- db:     SQLAlchemy 2.0 async engine + session 工厂
- logger: loguru 配置（双 sink）
- auth:   API key 鉴权（FastAPI Dependency）
"""
