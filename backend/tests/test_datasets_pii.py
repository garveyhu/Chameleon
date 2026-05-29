"""P21.1 PR #60 单元测试：dataset 采样 PII 脱敏与策略"""

from __future__ import annotations

from chameleon.system.datasets.pii import (
    apply_pii_strategy,
    apply_pii_strategy_dict,
    detect_pii,
    has_any_pii,
    mask_pii,
)

# ── 检测 ────────────────────────────────────────────────


def test_detect_pii_email():
    counts = detect_pii("联系 user@example.com 或 ops@foo.bar.com")
    assert counts["email"] == 2
    assert counts["phone"] == 0
    assert counts["id_card"] == 0


def test_detect_pii_phone_cn():
    counts = detect_pii("我的手机是 13812345678")
    assert counts["phone"] == 1


def test_detect_pii_phone_intl():
    counts = detect_pii("call +86-138-1234-5678")
    assert counts["phone"] >= 1


def test_detect_pii_id_card_18():
    # 110101 19900101 1234（最后位 X 也合法）
    counts = detect_pii("身份证 11010119900101123X")
    assert counts["id_card"] == 1


def test_detect_pii_id_card_15():
    counts = detect_pii("老身份证 110101900101123")
    assert counts["id_card"] == 1


def test_detect_pii_empty():
    assert detect_pii("") == {"email": 0, "phone": 0, "id_card": 0}


def test_detect_pii_no_match():
    assert detect_pii("普通文本，无 PII") == {
        "email": 0,
        "phone": 0,
        "id_card": 0,
    }


# ── mask ───────────────────────────────────────────────


def test_mask_email():
    out = mask_pii("发邮件给 a@b.com")
    assert "<EMAIL>" in out
    assert "a@b.com" not in out


def test_mask_phone_cn():
    out = mask_pii("call 13812345678 now")
    assert "<PHONE>" in out
    assert "13812345678" not in out


def test_mask_id_card_18():
    out = mask_pii("身份证 11010119900101123X 已记录")
    assert "<ID>" in out
    assert "11010119900101123X" not in out


def test_mask_combined():
    out = mask_pii("email a@b.com phone 13812345678 id 11010119900101123X")
    assert "<EMAIL>" in out
    assert "<PHONE>" in out
    assert "<ID>" in out
    assert "@" not in out  # email 完全替换
    assert "13812345678" not in out


def test_mask_no_change_when_clean():
    text = "这是一段干净文本，无 PII"
    assert mask_pii(text) == text


# ── has_any_pii ────────────────────────────────────────


def test_has_any_pii_true_email():
    assert has_any_pii("a@b.com") is True


def test_has_any_pii_false():
    assert has_any_pii("普通文本") is False


def test_has_any_pii_empty():
    assert has_any_pii("") is False


# ── apply_pii_strategy ────────────────────────────────


def test_apply_strategy_mask():
    out, dropped = apply_pii_strategy("email a@b.com here", "mask")
    assert dropped is False
    assert "<EMAIL>" in out
    assert "a@b.com" not in out


def test_apply_strategy_drop_when_has_pii():
    out, dropped = apply_pii_strategy("phone 13812345678", "drop")
    assert dropped is True
    assert out is None


def test_apply_strategy_drop_when_clean():
    out, dropped = apply_pii_strategy("clean text", "drop")
    assert dropped is False
    assert out == "clean text"


def test_apply_strategy_keep_preserves_pii():
    text = "email a@b.com"
    out, dropped = apply_pii_strategy(text, "keep")
    assert dropped is False
    assert out == text


def test_apply_strategy_empty_text_passes_through():
    out, dropped = apply_pii_strategy("", "drop")
    assert dropped is False
    assert out == ""


def test_apply_strategy_none_passes_through():
    out, dropped = apply_pii_strategy(None, "drop")
    assert dropped is False
    assert out is None


# ── apply_pii_strategy_dict ───────────────────────────


def test_apply_dict_mask_recursively():
    payload = {
        "user_input": "邮箱 a@b.com",
        "nested": {"phone": "13812345678"},
        "items": ["clean", "id 11010119900101123X"],
    }
    out, dropped = apply_pii_strategy_dict(payload, "mask")
    assert dropped is False
    assert "<EMAIL>" in out["user_input"]
    assert "<PHONE>" in out["nested"]["phone"]
    assert "<ID>" in out["items"][1]


def test_apply_dict_drop_on_any_pii():
    payload = {"q": "clean", "extra": {"contact": "a@b.com"}}
    out, dropped = apply_pii_strategy_dict(payload, "drop")
    assert dropped is True
    assert out is None


def test_apply_dict_drop_when_clean():
    payload = {"q": "just text", "n": 42, "flag": True}
    out, dropped = apply_pii_strategy_dict(payload, "drop")
    assert dropped is False
    assert out == payload


def test_apply_dict_none_returns_none():
    out, dropped = apply_pii_strategy_dict(None, "mask")
    assert dropped is False
    assert out is None


def test_apply_dict_preserves_non_string_types():
    payload = {"count": 5, "active": True, "ratio": 0.5, "nothing": None}
    out, dropped = apply_pii_strategy_dict(payload, "mask")
    assert dropped is False
    assert out == payload
