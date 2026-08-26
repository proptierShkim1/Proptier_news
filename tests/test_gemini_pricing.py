import gemini_pricing


def test_estimate_tokens_from_text_uses_calibrated_chars_per_token():
    text = "가" * 14  # 14자, 1.4자/토큰 기준 정확히 10토큰
    assert gemini_pricing.estimate_tokens_from_text(text) == 10


def test_estimate_tokens_from_text_returns_zero_for_empty_text():
    assert gemini_pricing.estimate_tokens_from_text("") == 0


def test_estimate_tokens_from_text_never_returns_zero_for_nonempty_text():
    assert gemini_pricing.estimate_tokens_from_text("가") >= 1


def test_estimate_cost_usd_uses_flash_pricing_for_summarizer():
    cost = gemini_pricing.estimate_cost_usd("summarizer", 1_000_000, 1_000_000)
    assert cost == 0.30 + 2.50


def test_estimate_cost_usd_uses_flash_pricing_for_agent_chat():
    cost = gemini_pricing.estimate_cost_usd("agent_chat", 1_000_000, 0)
    assert cost == 0.30


def test_estimate_cost_usd_uses_embedding_pricing_for_vectorizer():
    cost = gemini_pricing.estimate_cost_usd("vectorizer", 1_000_000, 0)
    assert cost == 0.15


def test_estimate_cost_usd_ignores_output_tokens_for_vectorizer():
    """벡터화는 실제로 output_tokens가 항상 0이지만, 혹시 값이 들어와도 임베딩
    단가에는 출력 단가 개념이 없으므로 무시되어야 한다."""
    cost = gemini_pricing.estimate_cost_usd("vectorizer", 1_000_000, 1_000_000)
    assert cost == 0.15
