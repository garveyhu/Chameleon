"""pydantic-settings 强类型 .env 绑定

★ 同时把 .env 加载到 os.environ：让 inventory.llm_provider_credential 这类
   靠 os.environ.get(key_env) 动态查询的代码也能看到 .env 里的变量
   （比如 agents.yaml 引用的 DIFY_FAQ_KEY / 用户自定义的 *_API_KEY）。
"""

from dotenv import load_dotenv
from pydantic import SecretStr
from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic_settings import SettingsConfigDict

from chameleon.core.config.constants import CONFIG_PATH

# 优先把 .env 写到 os.environ —— 在 EnvSettings 实例化前先做，
# 这样 pydantic-settings 也能拿到（pydantic-settings 优先级：
#   init kwargs > env var > .env file > secrets > 默认值
# 所以 load_dotenv 先注入到 env var 不会被 .env file 覆盖语义）。
_ENV_FILE = CONFIG_PATH / ".env"
if _ENV_FILE.exists():
    # override=False：os.environ 里已有的值优先（生产环境 env 注入）
    load_dotenv(_ENV_FILE, override=False)


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
