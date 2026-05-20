"""JSON 主题配置 —— 学 sage 风格

三个全局单例：
- chameleon_settings: 业务参数（chameleon.json）
- url_settings:       外部 URL 映射（baseurl.json）
- model_settings:     LLM/embedding 模型清单（model.json）
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
url_settings = _load("baseurl.json")
model_settings = _load("model.json")
