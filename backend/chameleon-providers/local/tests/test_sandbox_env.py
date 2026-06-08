"""沙箱环境擦除单测（T4-2 Phase 2 基石）：凭据绝不进子进程。"""

from __future__ import annotations

from chameleon.providers.local.sandbox import scrub_env


def test_scrub_env_drops_all_credentials():
    src = {
        "PATH": "/usr/bin",
        "HOME": "/home/x",
        "LC_ALL": "en_US.UTF-8",
        "DATABASE_URL": "postgres://u:p@h/db",
        "REDIS_PASSWORD": "secret",
        "MINIO_SECRET_KEY": "abc",
        "OPENAI_API_KEY": "sk-xxx",
        "CHAMELEON_DEV_TOKEN": "dev-tok",
        "SOME_SECRET": "s",
        "QWEN_DSN": "x",
        "GATEWAY_URL": "http://gw",
    }
    out = scrub_env(src)
    # 白名单透传
    assert out["PATH"] == "/usr/bin"
    assert out["HOME"] == "/home/x"
    assert out["LC_ALL"] == "en_US.UTF-8"
    # 标记
    assert out["CHAMELEON_SANDBOX"] == "1"
    # 凭据全部剔除
    for leaked in (
        "DATABASE_URL", "REDIS_PASSWORD", "MINIO_SECRET_KEY", "OPENAI_API_KEY",
        "CHAMELEON_DEV_TOKEN", "SOME_SECRET", "QWEN_DSN", "GATEWAY_URL",
    ):
        assert leaked not in out, f"凭据泄漏进沙箱: {leaked}"


def test_scrub_env_extra_still_filters_secrets():
    out = scrub_env({"PATH": "/b"}, extra={"PYTHONPATH": "/pkg/src", "X_API_KEY": "leak"})
    assert out["PYTHONPATH"] == "/pkg/src"  # 非凭据 extra 透传
    assert "X_API_KEY" not in out  # 凭据名 extra 仍被兜底剔除


def test_scrub_env_excludes_unknown_nonsecret():
    # 白名单外的普通变量也不透（最小 env）
    out = scrub_env({"PATH": "/b", "RANDOM_FLAG": "1"})
    assert "RANDOM_FLAG" not in out
