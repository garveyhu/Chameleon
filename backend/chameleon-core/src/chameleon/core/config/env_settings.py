"""pydantic-settings 强类型 .env 绑定

sage 风格重构后：AI key 进 model.json、DB 进 component.json，
.env **只保留部署级 override**（如多实例区分、容器化场景的 env 注入）。

仍然保留 .env 文件加载链路 —— 让 os.environ 看到 .env 内的变量，便于：
- 容器部署时通过 env 注入 override
- 测试用 monkeypatch.setenv 控制
- agents.yaml 用 `${env:XXX}` 占位符引用部署级变量
"""

from dotenv import load_dotenv
from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic_settings import SettingsConfigDict

from chameleon.core.config.constants import CONFIG_PATH

# 把 .env 写到 os.environ（让 ${env:X} 占位符 / monkeypatch / 动态查询都能用）
_ENV_FILE = CONFIG_PATH / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)


class EnvSettings(PydanticBaseSettings):
    """部署级 env 变量（可选 override 配置文件里的值）

    设计：所有字段都可选——配置已经在 model.json / component.json / chameleon.json 里。
    .env 只是给"部署时不想改 JSON"的用户一个出口。
    """

    # 日志级别（覆盖 chameleon.json log_level）
    LOG_LEVEL: str | None = None

    # 雪花 ID 实例号（多实例部署必须）
    CHAMELEON_INSTANCE_ID: int = 0

    # 数据库 URL override（如果设了就用这个，否则从 component.json 拼）
    DATABASE_URL: str | None = None

    # Redis 连接 override（容器化部署时通过 env 注入；任一字段为 None → 走 component.json）
    REDIS_HOST: str | None = None
    REDIS_PORT: int | None = None
    REDIS_DB: int | None = None
    REDIS_PASSWORD: str | None = None

    model_config = SettingsConfigDict(
        env_file=CONFIG_PATH / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 允许 .env 含额外变量（agents.yaml 占位符引用等）
    )


env_settings = EnvSettings()
