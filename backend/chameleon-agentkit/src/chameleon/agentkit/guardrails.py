"""agentkit guardrails —— 声明式输入/输出安全轨道（T2-1）。

`@agent(guardrails=[...])` 声明一组轨道，运行时在 ctx.complete/stream/run_with_tools 的
**入口**跑 input 轨（注入/长度/PII 等）、**出口**跑 output 轨（PII 脱敏/输出 schema 等）；
命中按各轨道策略 action 处置：

- ``block``：拦截，抛 ``GuardrailViolation``（由 run 边界兜成 error 事件）。
- ``redact``：脱敏改写文本后放行（input 改 user / output 改回答）。
- ``retry``：仅 output——回答不合规则重跑 LLM（至 ``max_retries`` 次），仍不过则 block。
- ``warn``：只记日志不拦（误杀场景的 warn-only 模式）。

内置一组（注入/PII/长度/输出 schema）+ 扩展点（作者 subclass ``Guardrail`` 接外部
Llama Guard / 自定义分类模型等）。纯 stdlib + pydantic，agentkit lean SDK 不引重依赖。

红线：轻量校验优先（别拖慢主路径）；策略可配 warn-only（防误杀）。
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ValidationError

_log = logging.getLogger(__name__)

GuardStage = Literal["input", "output"]
GuardAction = Literal["block", "redact", "retry", "warn"]


class GuardrailViolation(Exception):
    """input/output 轨道判定 block 时抛出（运行时在 run 边界兜成 error 事件）。"""

    def __init__(self, guard: str, reason: str) -> None:
        super().__init__(f"guardrail {guard!r} 拦截：{reason}")
        self.guard = guard
        self.reason = reason


@dataclass(slots=True)
class GuardResult:
    """一条轨道 check 的结论。

    action：命中后的处置（block/redact/retry/warn）；未命中 = ``None``（放行）。
    text：redact 时为脱敏后文本，其余沿用原文。
    """

    action: GuardAction | None = None
    text: str = ""
    reason: str = ""


class Guardrail(ABC):
    """一条安全轨道的基类。作者 subclass 即可接入自定义/外部校验（如 Llama Guard）。

    Attributes:
        name: 轨道名（trace / 报错展示）。
        stage: "input"（跑在 user 文本上）或 "output"（跑在 LLM 回答上）。
        action: 命中后的处置策略。
        max_retries: action="retry" 时的最大重跑次数（仅 output 生效）。
    """

    name: str = "guardrail"
    stage: GuardStage = "input"
    action: GuardAction = "block"
    max_retries: int = 2

    @abstractmethod
    async def check(self, text: str) -> GuardResult:
        """检查 text；命中返带 action 的 GuardResult，未命中返 ``GuardResult()``（action=None）。"""
        ...


# ── 内置轨道 ────────────────────────────────────────────────

#: 提示注入常见模式（中英；越权改写系统指令 / 忽略上文）
_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+)?(the\s+)?(previous|above|prior)\s+(instructions?|prompts?)",
        r"disregard\s+(the\s+)?(above|previous|prior|all)",
        r"forget\s+(everything|all|the\s+above|previous\s+instructions?)",
        r"you\s+are\s+now\s+(a|an|the)\b",
        r"new\s+(instructions?|system\s+prompt)\s*[:：]",
        r"reveal\s+(your\s+)?(system\s+prompt|instructions?)",
        r"忽略(以上|之前|前面|上面)(的)?(所有)?(指令|提示|要求)",
        r"无视(上面|之前|前面|以上)(的)?(指令|提示|要求)",
        r"忘(记|掉)(之前|以上|前面)(的)?(所有)?(指令|对话)",
        r"你现在(是|扮演)",
    )
]


class NoInjection(Guardrail):
    """input 轨：拦截提示注入（越权改写系统指令 / 忽略上文）。默认 block。"""

    name = "no_injection"
    stage: GuardStage = "input"

    def __init__(self, *, action: GuardAction = "block") -> None:
        self.action = action

    async def check(self, text: str) -> GuardResult:
        for pat in _INJECTION_PATTERNS:
            m = pat.search(text or "")
            if m:
                return GuardResult(
                    action=self.action, text=text,
                    reason=f"疑似提示注入：{m.group(0)[:60]!r}",
                )
        return GuardResult()


class MaxLen(Guardrail):
    """input 轨：限制输入长度（防超长 prompt 轰炸 / 成本失控）。默认 block。"""

    name = "max_len"
    stage: GuardStage = "input"

    def __init__(self, max_chars: int, *, action: GuardAction = "block") -> None:
        self.max_chars = int(max_chars)
        self.action = action

    async def check(self, text: str) -> GuardResult:
        n = len(text or "")
        if n > self.max_chars:
            return GuardResult(
                action=self.action, text=(text or "")[: self.max_chars],
                reason=f"输入超长 {n} > {self.max_chars}",
            )
        return GuardResult()


# PII 正则（与 datasets/pii.py 一致；agentkit lean SDK 自包含、不依赖 system）
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_PHONE_CN_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_PHONE_INTL_RE = re.compile(r"\+\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}")
_ID_CN_18_RE = re.compile(
    r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])"
    r"(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"
)
_ID_CN_15_RE = re.compile(
    r"(?<!\d)[1-9]\d{5}\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}(?!\d)"
)


def _mask_pii(text: str) -> tuple[str, bool]:
    """脱敏邮箱/手机/身份证为占位符；返 (脱敏文本, 是否命中)。"""
    out = _EMAIL_RE.sub("<EMAIL>", text or "")
    out = _PHONE_CN_RE.sub("<PHONE>", out)
    out = _PHONE_INTL_RE.sub("<PHONE>", out)
    out = _ID_CN_18_RE.sub("<ID>", out)
    out = _ID_CN_15_RE.sub("<ID>", out)
    return out, out != (text or "")


class PiiRedact(Guardrail):
    """PII 脱敏轨：邮箱/手机/身份证 → 占位符。默认 output（脱敏回答）；可设 stage="input"。"""

    name = "pii_redact"

    def __init__(
        self, *, stage: GuardStage = "output", action: GuardAction = "redact"
    ) -> None:
        self.stage = stage
        self.action = action

    async def check(self, text: str) -> GuardResult:
        masked, hit = _mask_pii(text or "")
        if hit:
            return GuardResult(action=self.action, text=masked, reason="命中 PII，已脱敏")
        return GuardResult()


class OutputJsonSchema(Guardrail):
    """output 轨：回答须是合法 JSON 且匹配 pydantic schema，违例 retry（重跑 LLM）。

    用于文本 complete 要求结构化输出但不走 with_structured_output 的场景；retry 耗尽则 block。
    """

    name = "output_json_schema"
    stage: GuardStage = "output"

    def __init__(self, schema: type[BaseModel], *, max_retries: int = 2) -> None:
        self.schema = schema
        self.action: GuardAction = "retry"
        self.max_retries = int(max_retries)

    async def check(self, text: str) -> GuardResult:
        try:
            data = json.loads(text or "")
        except (json.JSONDecodeError, TypeError):
            return GuardResult(action="retry", text=text, reason="输出非合法 JSON")
        try:
            self.schema.model_validate(data)
        except ValidationError as e:
            return GuardResult(
                action="retry", text=text,
                reason=f"输出不匹配 schema：{str(e)[:120]}",
            )
        return GuardResult()


# ── 运行时编排（供 _runtime.py 调用） ──────────────────────


async def run_input_guards(guards: list[Guardrail], text: str) -> str:
    """跑全部 input 轨：block→抛、redact→改写、warn→记日志。返最终（可能脱敏的）文本。"""
    for g in guards:
        if g.stage != "input":
            continue
        res = await g.check(text)
        if res.action is None:
            continue
        if res.action == "warn":
            _log.warning("guardrail %s warn：%s", g.name, res.reason)
        elif res.action == "redact":
            text = res.text
        else:  # block / retry（input 无 retry 语义 → 当 block）
            raise GuardrailViolation(g.name, res.reason)
    return text


async def run_output_guards(guards: list[Guardrail], text: str) -> GuardResult:
    """跑全部 output 轨，返聚合处置：block > retry > redact > 放行（优先级）。

    redact 累积改写；命中 retry 立即返（让调用方重跑 LLM）；命中 block 立即抛。
    """
    action: GuardAction | None = None
    for g in guards:
        if g.stage != "output":
            continue
        res = await g.check(text)
        if res.action is None:
            continue
        if res.action == "warn":
            _log.warning("guardrail %s warn：%s", g.name, res.reason)
        elif res.action == "block":
            raise GuardrailViolation(g.name, res.reason)
        elif res.action == "retry":
            return GuardResult(action="retry", text=text, reason=f"{g.name}: {res.reason}")
        elif res.action == "redact":
            text = res.text
            action = "redact"
    return GuardResult(action=action, text=text)


def output_retry_budget(guards: list[Guardrail]) -> int:
    """output 轨里 retry 类轨道的最大重跑预算（取最大）。"""
    return max(
        (g.max_retries for g in guards if g.stage == "output" and g.action == "retry"),
        default=0,
    )
