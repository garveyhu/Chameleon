"""DB seed 模块

启动期：DB users 表为空 → 从 config/*.json + namespace 扫描导入 → 落 DB。
后续以 DB 为唯一 source of truth；JSON 仅作为初始 seed + 备份载体。

主入口：`run_seed_if_empty()`，在 chameleon-app lifespan 中调用。
"""

from chameleon.system.seed.runner import run_seed_if_empty

__all__ = ["run_seed_if_empty"]
