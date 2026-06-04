"""DSL 文本解析器 —— 文本 DSL → DslSpec（纯函数、零 IO，重健壮性）。

语法（行级，逐行独立解析，非法行收集进 errors 不整体崩溃）：

    # 注释行（井号开头，整行跳过）
    answer: contains                  # 字段规则（无参）
    answer: regex: pattern=^\\d+$       # 字段规则（带参 k=v,k=v）
    answer: length_lte: n=200 *2      # 行尾 *权重
    > 回答要专业且无事实错误           # 自然语言规则（> 开头）
    > 回答需给出引用 *2               # 自然语言规则带权重

容错点：
- 中英文冒号（: ：）、中英文逗号（, ，）均接受。
- 空行 / 注释行跳过。
- 行尾 `*数字` 解析为权重（缺省 1.0）。
- 非法行（无冒号且非 > 开头、未知结构、权重非数等）收集到 errors，附行号 + 原文。
- 全空 / 全注释 → 空 spec + 一条提示 error。

parse(text) 返回 (DslSpec, errors)。func 名是否合法不在此校验（evaluator 求值时
按 DSL_FUNCTIONS 查找，未知则该条跳过并标注），parser 只负责结构解析。
"""

from __future__ import annotations

import re

from chameleon.system.datasets.dsl.spec import DslSpec, FieldRule, NlRule

# 中英文冒号 / 逗号归一
_COLON_RE = re.compile(r"[:：]")
_COMMA_RE = re.compile(r"[,，]")
# 行尾权重：* 后跟数字（允许小数），前可有空白
_WEIGHT_RE = re.compile(r"\*\s*([0-9]+(?:\.[0-9]+)?)\s*$")


def _split_weight(line: str) -> tuple[str, float]:
    """剥离行尾 `*权重`，返回 (去权重后的正文, 权重)。

    无合法 `*数字` 标记则权重默认 1.0、正文原样返回（行尾裸 `*` 或非数字权重当作
    正文一部分，留给后续结构解析报错，不在此单独拦）。
    """
    m = _WEIGHT_RE.search(line)
    if not m:
        return line, 1.0
    return line[: m.start()].rstrip(), float(m.group(1))


def _parse_args(raw: str) -> dict[str, str]:
    """解析 `k1=v1,k2=v2`（中英逗号均吃）为字典；空段 / 无等号段跳过。"""
    args: dict[str, str] = {}
    for seg in _COMMA_RE.split(raw):
        seg = seg.strip()
        if not seg or "=" not in seg:
            continue
        key, _, val = seg.partition("=")
        key = key.strip()
        if key:
            args[key] = val.strip()
    return args


def _parse_field_rule(
    body: str, weight: float, line_no: int, original: str
) -> tuple[FieldRule | None, str | None]:
    """解析字段规则行 `field: func[: args]`，返回 (规则或 None, 错误信息或 None)。"""
    parts = _COLON_RE.split(body)
    # 去除每段首尾空白
    parts = [p.strip() for p in parts]
    if len(parts) < 2:
        return None, f"第 {line_no} 行无法识别（缺函数名）: {original!r}"
    field_name = parts[0]
    func = parts[1]
    if not field_name:
        return None, f"第 {line_no} 行字段名为空: {original!r}"
    if not func:
        return None, f"第 {line_no} 行函数名为空: {original!r}"
    # 第三段及之后合并为参数串（容错参数里再含冒号的少见场景）
    args_raw = ":".join(parts[2:]).strip() if len(parts) > 2 else ""
    args = _parse_args(args_raw) if args_raw else {}
    return FieldRule(field=field_name, func=func, args=args, weight=weight), None


def parse(text: str) -> tuple[DslSpec, list[str]]:
    """解析 DSL 文本为 DslSpec 加错误列表。

    Args:
        text: 用户输入的 DSL 文本（多行）。

    Returns:
        (DslSpec, errors)：errors 是逐行收集的可读错误（含行号 + 原文）；
        全空 / 全注释时返回空 spec 加一条提示。
    """
    spec = DslSpec()
    errors: list[str] = []
    raw_text = text or ""

    saw_content = False
    for idx, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        saw_content = True

        body, weight = _split_weight(line)

        if body.startswith(">"):
            desc = body[1:].strip()
            if not desc:
                errors.append(f"第 {idx} 行自然语言规则为空: {raw_line!r}")
                continue
            spec.nl_rules.append(NlRule(description=desc, weight=weight))
            continue

        if not _COLON_RE.search(body):
            errors.append(
                f"第 {idx} 行无法识别（既非 > 规则也非 field:func）: {raw_line!r}"
            )
            continue

        rule, rule_err = _parse_field_rule(body, weight, idx, raw_line)
        if rule_err:
            errors.append(rule_err)
            continue
        if rule is not None:
            spec.field_rules.append(rule)

    if not saw_content:
        errors.append("DSL 为空或仅含注释，无有效规则")

    return spec, errors
