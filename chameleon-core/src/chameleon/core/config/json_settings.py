"""JSON 主题配置 —— 学 sage 风格

四个全局单例（sage 习惯：AI 全包 + 中间件分离）：
- chameleon_settings: 业务参数（chameleon.json）—— log_level / session / knowledge / stream 等
- model_settings:     LLM/embedding 全包（model.json）—— cases / providers(含 key+url) / models
- component_settings: 中间件连接（component.json）—— database / redis / 其它
- url_settings:       外部 agent 平台 URL（baseurl.json）—— 仅 DIFY/FastGPT 等编排平台

> sage 原 model.json 里 keys 字段明文存 API key 已是惯例；chameleon 的 model.json
> 同样 .gitignore，安全。
"""

from chameleon.core.config.base_settings import BaseSettings
from chameleon.core.config.constants import CONFIG_PATH


def _load(name: str) -> BaseSettings:
    """从 config/<name>.json 加载，文件不存在则返回空容器"""
    path = CONFIG_PATH / name
    if not path.exists():
        return BaseSettings({})
    return BaseSettings.from_json(path)


chameleon_settings = _load("chameleon.json")
model_settings = _load("model.json")
component_settings = _load("component.json")
url_settings = _load("baseurl.json")
