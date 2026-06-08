"""agentkit dev 热重载核心：_reload_and_resolve 重载作者模块不撞「重复声明的 agent key」
（@agent 登记在模块级 _DECLARED，重载前须清掉该模块的登记），且重新解析出 manifest。
"""

from __future__ import annotations

import sys

import pytest

from chameleon.agentkit._cli import _load_manifest, _reload_and_resolve

_MOD = "_dev_reload_probe_mod"
_SRC_V1 = """
from chameleon.agentkit import AgentRun, ModelSlot, agent

@agent(key="_dev_reload_probe", name="v1", models=[ModelSlot("chat", "c")])
async def handle(ctx: AgentRun):
    yield "v1"
"""
_SRC_V2 = _SRC_V1.replace('name="v1"', 'name="v2"').replace('yield "v1"', 'yield "v2"')


@pytest.fixture
def _probe_module(tmp_path, monkeypatch):
    f = tmp_path / f"{_MOD}.py"
    f.write_text(_SRC_V1)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield f
    # 清理 _DECLARED + sys.modules，免污染其它测试
    from chameleon.agentkit import _decorator

    _decorator._DECLARED.pop("_dev_reload_probe", None)
    sys.modules.pop(_MOD, None)


def test_reload_no_duplicate_declaration(_probe_module):
    man1 = _load_manifest(_MOD)
    assert man1.key == "_dev_reload_probe" and man1.name == "v1"
    # 重载不应抛"重复声明的 agent key"（dev watch 每次文件变更都会调它）
    man2 = _reload_and_resolve(_MOD)
    assert man2.key == "_dev_reload_probe"


def test_reload_picks_up_edits(_probe_module):
    import os

    assert _load_manifest(_MOD).name == "v1"
    _probe_module.write_text(_SRC_V2)  # 模拟作者编辑
    # bump mtime 模拟真实编辑（watch 按 mtime 变化触发；测试同秒双写需显式 +2s 越过秒粒度缓存）
    st = _probe_module.stat()
    os.utime(_probe_module, (st.st_atime + 2, st.st_mtime + 2))
    man = _reload_and_resolve(_MOD)
    assert man.name == "v2", "热重载应取到编辑后的新声明"
