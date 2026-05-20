"""pydantic-settings 强类型 .env 绑定"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic_settings import SettingsConfigDict

from chameleon.core.config.constants import CONFIG_PATH


class EnvSettings(PydanticBaseSettings):
    """敏感 / 强类型环境变量（绑定 config/.env）

    业务参数走 chameleon.json / model.json 等；这里只放敏感或必需启动的变量。
    """

    # DB
    DATABASE_URL: str
    REDIS_URL: str | None = None

    # 日志
    LOG_LEVEL: str = "INFO"

    # 雪花 ID 实例号
    CHAMELEON_INSTANCE_ID: int = 0

    # LLM provider keys（按需，可空）
    OPENAI_API_KEY: SecretStr | None = None
    DEEPSEEK_API_KEY: SecretStr | None = None
    QWEN_API_KEY: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=CONFIG_PATH / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 允许 .env 里有 agents.yaml 引用的额外 KEY（如 DIFY_FAQ_KEY）
    )


env_settings = EnvSettings()
