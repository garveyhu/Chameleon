"""沙箱子进程环境擦除 —— 凭据隔离（T4-2 Phase 2 基石）。

子进程即便被注入恶意代码也读不到任何凭据（DB/Redis/MinIO/API key/dev token）：只透传
运行所需的白名单变量 + 标记 CHAMELEON_SANDBOX=1。凭据只留主进程，ctx 资源访问经 broker。

红线（见 sandbox-phase2-design §4）：白名单准入，黑名单兜底——既白名单外不透，又对疑似
凭据名（含 SECRET/KEY/TOKEN/PASSWORD/DSN/URL 等）显式剔除，防新增凭据变量漏网。
"""

from __future__ import annotations

import re

#: 明确透传的环境变量（子进程运行 Python + 定位 agentkit/作者包所需）
_ALLOW_EXACT = {"PATH", "HOME", "PYTHONPATH", "LANG", "TZ", "TMPDIR", "PYTHONHASHSEED"}
_ALLOW_PREFIX = ("LC_",)

#: 疑似凭据名模式 —— 即便不在白名单也兜底剔除（防呆）
_SECRET_PATTERN = re.compile(
    r"(SECRET|PASSWORD|PASSWD|TOKEN|API_?KEY|ACCESS_?KEY|PRIVATE|CREDENTIAL|"
    r"_DSN$|DATABASE_URL|REDIS|MINIO|_URL$)",
    re.IGNORECASE,
)


def _allowed(key: str) -> bool:
    if key in _ALLOW_EXACT:
        return True
    return any(key.startswith(p) for p in _ALLOW_PREFIX)


def scrub_env(source: dict[str, str], *, extra: dict[str, str] | None = None) -> dict[str, str]:
    """从 source 产出沙箱子进程的最小 env：白名单准入 + 凭据名兜底剔除 + 注入 extra。

    Args:
        source: 原始环境（通常 os.environ）。
        extra: 额外透传（如 PYTHONPATH 补作者包路径）；不受白名单限制，但仍过凭据兜底。

    Returns:
        擦除后的 env dict（含 CHAMELEON_SANDBOX=1 标记）。
    """
    out: dict[str, str] = {}
    for k, v in source.items():
        if _allowed(k) and not _SECRET_PATTERN.search(k):
            out[k] = v
    for k, v in (extra or {}).items():
        if not _SECRET_PATTERN.search(k):
            out[k] = v
    out["CHAMELEON_SANDBOX"] = "1"
    return out
