from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

import agent_chat
import cached_db


@pytest.fixture(autouse=True)
def _stub_api_usage_logging(monkeypatch):
    """이 파일의 거의 모든 테스트가 _send_with_key_failover를 거치고, 거기서 이제
    db.insert_api_usage를 호출한다. MagicMock 응답의 usage_metadata는 실제 int가 아니라
    MagicMock이라 그대로 두면 진짜 DB에 잘못된 값을 쓰려 든다 — 사용량 로깅 자체를
    검증하는 테스트를 빼고는 기본적으로 no-op 처리한다."""
    monkeypatch.setattr(agent_chat.db, "insert_api_usage", lambda *a, **kw: None)


@pytest.fixture(autouse=True)
def _clear_cached_db():
    """_STATS_TOOLS는 이제 db.py를 직접 부르지 않고 cached_db.py를 거친다(다중 사용자
    동시 질문 시 DB 재조회를 줄이기 위한 캐싱). st.cache_data는 프로세스 전역 캐시라
    앞선 테스트가 채워둔 값이 다음 테스트에도 그대로 남을 수 있어, 매 테스트 전에
    비운다."""
    cached_db.clear()


def test_has_api_keys_reflects_configured_keys(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: [])
    assert agent_chat.has_api_keys() is False

    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    assert agent_chat.has_api_keys() is True


def test_ask_returns_error_message_when_no_keys_configured(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: [])

    result = agent_chat.ask([], "안녕")

    assert "GEMINI_API_KEYS" in result


def test_ask_creates_a_fresh_client_and_chat_per_call(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    monkeypatch.setattr(agent_chat.summarizer, "_model_name", lambda: "gemini-2.5-flash")
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = MagicMock(text="안녕하세요!")
    fake_client = MagicMock()
    fake_client.chats.create.return_value = fake_chat

    with patch.object(agent_chat.genai, "Client", return_value=fake_client) as mock_ctor:
        result = agent_chat.ask([], "안녕")

    mock_ctor.assert_called_once_with(api_key="key1")
    fake_client.chats.create.assert_called_once()
    assert fake_client.chats.create.call_args.kwargs["model"] == "gemini-2.5-flash"
    fake_chat.send_message.assert_called_once_with("안녕")
    assert result == "안녕하세요!"


def test_ask_seeds_prior_history_into_the_new_chat_session(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = MagicMock(text="응답")
    fake_client = MagicMock()
    fake_client.chats.create.return_value = fake_chat

    history = [
        {"role": "user", "content": "내 이름은 철수야"},
        {"role": "assistant", "content": "안녕 철수!"},
    ]

    with patch.object(agent_chat.genai, "Client", return_value=fake_client):
        agent_chat.ask(history, "내 이름이 뭐라고 했지?")

    seeded = fake_client.chats.create.call_args.kwargs["history"]
    assert len(seeded) == 2
    assert seeded[0].role == "user"
    assert seeded[1].role == "model"


def test_ask_tries_next_key_when_first_fails(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["bad-key", "good-key"])
    failing_client = MagicMock()
    failing_client.chats.create.side_effect = Exception("client has been closed")
    working_chat = MagicMock()
    working_chat.send_message.return_value = MagicMock(text="복구된 응답")
    working_client = MagicMock()
    working_client.chats.create.return_value = working_chat

    with patch.object(agent_chat.genai, "Client", side_effect=[failing_client, working_client]):
        result = agent_chat.ask([], "안녕")

    assert result == "복구된 응답"


def test_ask_returns_fallback_message_when_all_keys_fail(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    failing_client = MagicMock()
    failing_client.chats.create.side_effect = Exception("boom")

    with patch.object(agent_chat.genai, "Client", return_value=failing_client):
        result = agent_chat.ask([], "안녕")

    assert "실패" in result


def test_ask_appends_context_to_system_instruction_when_provided(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = MagicMock(text="응답")
    fake_client = MagicMock()
    fake_client.chats.create.return_value = fake_chat

    with patch.object(agent_chat.genai, "Client", return_value=fake_client):
        agent_chat.ask([], "직방 최근 동향 알려줘", context="- [뉴스] 직방 관련 소식")

    instruction = fake_client.chats.create.call_args.kwargs["config"]["system_instruction"]
    assert "직방 관련 소식" in instruction


def test_ask_uses_no_context_note_when_context_is_empty(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = MagicMock(text="응답")
    fake_client = MagicMock()
    fake_client.chats.create.return_value = fake_chat

    with patch.object(agent_chat.genai, "Client", return_value=fake_client):
        agent_chat.ask([], "안녕")

    instruction = fake_client.chats.create.call_args.kwargs["config"]["system_instruction"]
    assert "찾지 못했" in instruction


def test_build_grounding_context_formats_mention_and_policy_hits():
    mention_hits = [
        {"title": "직방 신규 서비스 출시", "brand": "직방", "posted_at": "2026-08-01", "summary": "직방이 새 서비스를 냈다."},
    ]
    policy_hits = [
        {"title": "국토부 규제 발표", "source": "국토부", "announced_at": "2026-08-02"},
    ]

    context = agent_chat.build_grounding_context(mention_hits, policy_hits)

    assert "직방 신규 서비스 출시" in context
    assert "직방이 새 서비스를 냈다." in context
    assert "국토부 규제 발표" in context


def test_build_grounding_context_returns_empty_string_when_no_hits():
    assert agent_chat.build_grounding_context([], []) == ""


def test_is_grounding_sufficient_true_when_best_distance_within_threshold():
    mention_hits = [{"distance": 0.79}, {"distance": 0.95}]
    assert agent_chat.is_grounding_sufficient(mention_hits, []) is True


def test_is_grounding_sufficient_false_when_all_distances_exceed_threshold():
    mention_hits = [{"distance": 0.91}]
    policy_hits = [{"distance": 0.88}]
    assert agent_chat.is_grounding_sufficient(mention_hits, policy_hits) is False


def test_is_grounding_sufficient_false_when_no_hits_at_all():
    assert agent_chat.is_grounding_sufficient([], []) is False


def test_is_grounding_sufficient_uses_best_distance_across_both_sources():
    mention_hits = [{"distance": 0.95}]
    policy_hits = [{"distance": 0.5}]
    assert agent_chat.is_grounding_sufficient(mention_hits, policy_hits) is True


def test_is_grounding_sufficient_respects_custom_threshold():
    mention_hits = [{"distance": 0.5}]
    assert agent_chat.is_grounding_sufficient(mention_hits, [], threshold=0.3) is False


def test_looks_like_stats_only_question_matches_clear_stat_questions():
    assert agent_chat.looks_like_stats_only_question("오늘 뉴스 몇 건 수집됐어?") is True
    assert agent_chat.looks_like_stats_only_question("이번달 API 비용 얼마 나왔어?") is True
    assert agent_chat.looks_like_stats_only_question("벡터화 현황 알려줘") is True
    assert agent_chat.looks_like_stats_only_question("요즘 가장 많이 언급된 브랜드가 뭐야?") is True
    assert agent_chat.looks_like_stats_only_question("우리가 추적하는 브랜드 목록 보여줘") is True


def test_looks_like_stats_only_question_ignores_spacing():
    assert agent_chat.looks_like_stats_only_question("오늘몇건모였어") is True


def test_looks_like_stats_only_question_false_for_content_questions():
    assert agent_chat.looks_like_stats_only_question("직방 최근 동향 알려줘") is False
    assert agent_chat.looks_like_stats_only_question("부동산 정책 관련해서 요즘 이슈가 뭐야?") is False
    assert agent_chat.looks_like_stats_only_question("안녕") is False


def test_ask_with_web_search_returns_error_message_when_no_keys_configured(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: [])

    result = agent_chat.ask_with_web_search([], "화성 이주 계획 알려줘")

    assert "GEMINI_API_KEYS" in result


def test_ask_with_web_search_attaches_google_search_tool(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = MagicMock(text="웹 검색 기반 답변")
    fake_client = MagicMock()
    fake_client.chats.create.return_value = fake_chat

    with patch.object(agent_chat.genai, "Client", return_value=fake_client):
        result = agent_chat.ask_with_web_search([], "화성 이주 계획 알려줘")

    config = fake_client.chats.create.call_args.kwargs["config"]
    assert len(config["tools"]) == 1
    assert "웹 검색" in config["system_instruction"]
    fake_chat.send_message.assert_called_once_with("화성 이주 계획 알려줘")
    assert result == "웹 검색 기반 답변"


def test_ask_with_web_search_seeds_prior_history(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = MagicMock(text="응답")
    fake_client = MagicMock()
    fake_client.chats.create.return_value = fake_chat

    history = [{"role": "user", "content": "이전 질문"}, {"role": "assistant", "content": "이전 답변"}]

    with patch.object(agent_chat.genai, "Client", return_value=fake_client):
        agent_chat.ask_with_web_search(history, "다음 질문")

    seeded = fake_client.chats.create.call_args.kwargs["history"]
    assert len(seeded) == 2
    assert seeded[0].role == "user"
    assert seeded[1].role == "model"


def test_ask_with_web_search_tries_next_key_when_first_fails(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["bad-key", "good-key"])
    failing_client = MagicMock()
    failing_client.chats.create.side_effect = Exception("boom")
    working_chat = MagicMock()
    working_chat.send_message.return_value = MagicMock(text="복구된 응답")
    working_client = MagicMock()
    working_client.chats.create.return_value = working_chat

    with patch.object(agent_chat.genai, "Client", side_effect=[failing_client, working_client]):
        result = agent_chat.ask_with_web_search([], "화성 이주 계획 알려줘")

    assert result == "복구된 응답"


def test_ask_with_web_search_returns_fallback_message_when_all_keys_fail(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    failing_client = MagicMock()
    failing_client.chats.create.side_effect = Exception("boom")

    with patch.object(agent_chat.genai, "Client", return_value=failing_client):
        result = agent_chat.ask_with_web_search([], "화성 이주 계획 알려줘")

    assert "실패" in result


def test_get_channel_counts_groups_mentions_by_channel(monkeypatch):
    monkeypatch.setattr(
        agent_chat.cached_db, "get_mentions_by_collected_date",
        lambda date: [
            {"channel": "네이버", "title": "a"},
            {"channel": "네이버", "title": "b"},
            {"channel": "매경API", "title": "c"},
        ],
    )

    result = agent_chat.get_channel_counts("2026-08-13")

    assert result == {"네이버": 2, "매경API": 1}


def test_get_channel_counts_returns_empty_dict_when_no_mentions(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "get_mentions_by_collected_date", lambda date: [])

    assert agent_chat.get_channel_counts("2026-01-01") == {}


def test_get_overview_stats_aggregates_all_counts(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "count_mentions", lambda: 100)
    monkeypatch.setattr(agent_chat.cached_db, "count_policy_events", lambda: 40)
    monkeypatch.setattr(agent_chat.cached_db, "count_mention_vector_index", lambda: 90)
    monkeypatch.setattr(agent_chat.cached_db, "count_policy_vector_index", lambda: 35)
    monkeypatch.setattr(agent_chat.cached_db, "get_archived_briefing_dates", lambda: {"2026-08-10", "2026-08-11"})

    result = agent_chat.get_overview_stats()

    assert result == {
        "total_mentions": 100,
        "total_policy_events": 40,
        "vectorized_mentions": 90,
        "vectorized_policy_events": 35,
        "archived_briefing_days": 2,
    }


def test_get_brand_mention_count_delegates_to_db(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "count_mentions_by_brand", lambda brand: 42 if brand == "직방" else 0)

    assert agent_chat.get_brand_mention_count("직방") == 42
    assert agent_chat.get_brand_mention_count("없는브랜드") == 0


def test_get_policy_source_counts_delegates_to_db(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "get_policy_source_counts", lambda: {"국토부": 5, "LH": 3})

    assert agent_chat.get_policy_source_counts() == {"국토부": 5, "LH": 3}


def test_ask_passes_stats_tools_and_todays_date_in_system_instruction(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = MagicMock(text="응답")
    fake_client = MagicMock()
    fake_client.chats.create.return_value = fake_chat

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 13, 15, 0, 0)

    monkeypatch.setattr(agent_chat, "datetime", _FixedDatetime)

    with patch.object(agent_chat.genai, "Client", return_value=fake_client):
        agent_chat.ask([], "오늘 채널별로 몇 건씩 수집됐어?")

    config = fake_client.chats.create.call_args.kwargs["config"]
    assert config["tools"] == agent_chat._STATS_TOOLS
    assert "2026-08-13" in config["system_instruction"]


def test_ask_logs_api_usage_with_token_counts_on_success(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    monkeypatch.setattr(agent_chat.db, "insert_api_usage", lambda *a, **kw: None)
    usage = MagicMock(
        prompt_token_count=10, candidates_token_count=5,
        thoughts_token_count=20, total_token_count=35,
    )
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = MagicMock(text="응답", usage_metadata=usage)
    fake_client = MagicMock()
    fake_client.chats.create.return_value = fake_chat

    with patch.object(agent_chat.genai, "Client", return_value=fake_client), \
         patch.object(agent_chat.db, "insert_api_usage") as mock_usage:
        agent_chat.ask([], "안녕")

    mock_usage.assert_called_once_with(
        "agent_chat", agent_chat.summarizer._model_name(), ok=True,
        prompt_tokens=10, output_tokens=5, thoughts_tokens=20, total_tokens=35,
    )


def test_ask_logs_api_usage_as_failed_when_all_keys_fail(monkeypatch):
    monkeypatch.setattr(agent_chat.summarizer, "_load_api_keys", lambda: ["key1"])
    failing_client = MagicMock()
    failing_client.chats.create.side_effect = Exception("boom")

    with patch.object(agent_chat.genai, "Client", return_value=failing_client), \
         patch.object(agent_chat.db, "insert_api_usage") as mock_usage:
        agent_chat.ask([], "안녕")

    mock_usage.assert_called_once_with("agent_chat", agent_chat.summarizer._model_name(), ok=False)


def test_get_briefing_highlights_returns_archived_content_when_available(monkeypatch):
    archived = {
        "total_count": 5, "channel_counts": {"네이버": 5}, "channel_top_news": {"네이버": []},
        "own_brand_news": [], "competitor_news": [], "market_news": [],
    }
    monkeypatch.setattr(agent_chat.cached_db, "get_briefing_archive", lambda date: archived)

    result = agent_chat.get_briefing_highlights("2026-08-10")

    assert result["found"] is True
    assert result["total_count"] == 5
    assert result["channel_counts"] == {"네이버": 5}


def test_get_briefing_highlights_computes_live_when_not_yet_archived(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "get_briefing_archive", lambda date: None)
    monkeypatch.setattr(agent_chat.cached_db, "get_mentions_by_collected_date", lambda date: [{"id": 1}])
    monkeypatch.setattr(agent_chat.news_feed, "own_brand_names", lambda: {"프롭티어"})
    monkeypatch.setattr(agent_chat.news_feed, "competitor_brand_names", lambda: {"직방"})
    monkeypatch.setattr(agent_chat.news_feed, "market_brand_names", lambda: {"AI"})
    live_content = {
        "total_count": 1, "channel_counts": {"네이버": 1}, "channel_top_news": {},
        "own_brand_news": [], "competitor_news": [], "market_news": [],
    }
    monkeypatch.setattr(
        agent_chat.news_feed, "build_briefing_archive_content",
        lambda mentions, own, comp, mkt: live_content,
    )

    result = agent_chat.get_briefing_highlights("2026-08-14")

    assert result["found"] is True
    assert result["total_count"] == 1


def test_get_briefing_highlights_returns_not_found_when_no_data_at_all(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "get_briefing_archive", lambda date: None)
    monkeypatch.setattr(agent_chat.cached_db, "get_mentions_by_collected_date", lambda date: [])

    assert agent_chat.get_briefing_highlights("2026-01-01") == {"found": False}


def test_get_collection_health_reports_last_batch_per_channel_group(monkeypatch):
    def fake_run_batches(limit, channels):
        if channels == ("네이버", "구글", "다음", "커뮤니티"):
            return [{"ran_at": "2026-08-14 09:00:00", "trigger": "자동", "ok": 1, "message": ""}]
        if channels == ("매경API",):
            return [{"ran_at": "2026-08-14 08:00:00", "trigger": "수동", "ok": 0, "message": "오류"}]
        return []

    monkeypatch.setattr(agent_chat.cached_db, "get_run_batches", fake_run_batches)
    monkeypatch.setattr(
        agent_chat.cached_db, "get_policy_run_batches",
        lambda limit: [{"ran_at": "2026-08-14 07:00:00", "trigger": "자동", "ok": 1, "message": ""}],
    )

    health = agent_chat.get_collection_health()

    assert health["신규 게시물"]["ok"] is True
    assert health["매경API"]["ok"] is False
    assert health["매경API"]["message"] == "오류"
    assert health["정부 정책"]["last_run_at"] == "2026-08-14 07:00:00"
    assert "네이버뉴스API" not in health


def test_compare_brand_mentions_returns_count_per_brand(monkeypatch):
    counts = {"직방": 42, "프롭티어": 7}
    monkeypatch.setattr(agent_chat.cached_db, "count_mentions_by_brand_since", lambda brand, days: counts[brand])

    result = agent_chat.compare_brand_mentions(["직방", "프롭티어"], days=30)

    assert result == {"직방": 42, "프롭티어": 7}


def test_get_vectorization_status_aggregates_counts(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "count_mentions", lambda: 100)
    monkeypatch.setattr(agent_chat.cached_db, "count_mentions_without_embedding", lambda: 10)
    monkeypatch.setattr(agent_chat.cached_db, "count_policy_events", lambda: 50)
    monkeypatch.setattr(agent_chat.cached_db, "count_policy_events_without_embedding", lambda: 2)

    assert agent_chat.get_vectorization_status() == {
        "mentions_total": 100, "mentions_pending": 10,
        "policy_events_total": 50, "policy_events_pending": 2,
    }


def test_get_top_mentioned_brands_delegates_to_db(monkeypatch):
    ranked = [{"brand": "직방", "count": 10}, {"brand": "다방", "count": 3}]
    monkeypatch.setattr(agent_chat.cached_db, "get_top_mentioned_brands", lambda days, limit: ranked)

    assert agent_chat.get_top_mentioned_brands(days=30, limit=5) == ranked


def test_get_news_category_counts_aggregates_across_mentions(monkeypatch):
    mentions = [
        {"title": "직방 AI 매물 추천 출시", "snippet": ""},
        {"title": "다방 신규 서비스 출시", "snippet": "AI 기반"},
    ]
    monkeypatch.setattr(agent_chat.cached_db, "get_mentions_since", lambda days: mentions)

    counts = agent_chat.get_news_category_counts(days=30)

    assert counts["신규 도입"] == 2
    assert counts["AI"] == 2


def test_get_policy_category_counts_aggregates_across_events(monkeypatch):
    events = [
        {"title": "임대주택 지원 사업 공고"},
        {"title": "주택 통계 조사 결과 발표"},
    ]
    monkeypatch.setattr(agent_chat.cached_db, "get_policy_events_since", lambda days: events)

    counts = agent_chat.get_policy_category_counts(days=30)

    assert counts["지원·사업"] == 1
    assert counts["통계·조사"] == 1


def test_compare_collection_periods_computes_change_and_percentage(monkeypatch):
    def fake_between(start, end):
        return {(7, 0): 30, (14, 7): 20}[(start, end)]

    monkeypatch.setattr(agent_chat.cached_db, "count_mentions_between", fake_between)

    result = agent_chat.compare_collection_periods(period_days=7)

    assert result["recent_period"] == {"days": 7, "count": 30}
    assert result["previous_period"] == {"days": 7, "count": 20}
    assert result["change"] == 10
    assert result["change_pct"] == 50.0


def test_compare_collection_periods_handles_zero_previous_period(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "count_mentions_between", lambda start, end: 0)

    result = agent_chat.compare_collection_periods(period_days=7)

    assert result["change_pct"] is None


def test_get_api_cost_summary_computes_estimated_cost_per_feature(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "get_api_usage_summary", lambda days: {
        "summarizer": {"calls": 2, "prompt_tokens": 1_000_000, "output_tokens": 0, "tokens": 1_000_000, "failed": 0},
        "agent_chat": {"calls": 1, "prompt_tokens": 0, "output_tokens": 1_000_000, "tokens": 1_000_000, "failed": 1},
    })

    result = agent_chat.get_api_cost_summary(days=30)

    assert result["by_feature"]["summarizer"]["estimated_cost_usd"] == 0.3
    assert result["by_feature"]["agent_chat"]["estimated_cost_usd"] == 2.5
    assert result["total_calls"] == 3
    assert result["total_tokens"] == 2_000_000
    assert result["total_estimated_cost_usd"] == 2.8


def test_get_api_cost_summary_returns_zero_totals_when_no_usage(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "get_api_usage_summary", lambda days: {})

    result = agent_chat.get_api_cost_summary(days=30)

    assert result == {
        "by_feature": {}, "total_calls": 0, "total_tokens": 0, "total_estimated_cost_usd": 0.0,
    }


def test_get_tracked_brands_groups_by_role(monkeypatch):
    monkeypatch.setattr(agent_chat.utils, "load_keywords", lambda: {"brands": [
        {"name": "프롭티어", "role": "own"},
        {"name": "직방", "role": "competitor"},
        {"name": "다방", "role": "competitor"},
        {"name": "AI", "role": "market"},
    ]})

    result = agent_chat.get_tracked_brands()

    assert result == {
        "own": ["프롭티어"], "competitor": ["직방", "다방"], "market": ["AI"],
    }


def test_get_pdf_report_stats_delegates_to_db(monkeypatch):
    monkeypatch.setattr(
        agent_chat.cached_db, "count_activity_log_by_action",
        lambda action, days: 7 if action == "PDF 생성" else 0,
    )

    assert agent_chat.get_pdf_report_stats(days=30) == {"count": 7}


def test_get_top_viewed_policy_events_delegates_to_db(monkeypatch):
    top = [{"title": "제목", "source": "국토부", "view_count": 500, "announced_at": "2026-08-01"}]
    monkeypatch.setattr(agent_chat.cached_db, "get_top_viewed_policy_events", lambda limit: top)

    assert agent_chat.get_top_viewed_policy_events(limit=5) == top


def _fix_now(monkeypatch, fixed):
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(agent_chat, "datetime", _FixedDatetime)


def test_search_mentions_filters_by_keyword_brand_and_recency(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 8, 20, 12, 0, 0))
    mentions = [
        {"title": "직방 AI 매물 추천", "url": "https://x/1", "channel": "네이버", "brand": "직방",
         "snippet": "", "collected_at": "2026-08-19 10:00:00"},
        {"title": "직방 관련없는 소식", "url": "https://x/2", "channel": "네이버", "brand": "직방",
         "snippet": "인사 발령 소식", "collected_at": "2026-08-18 10:00:00"},
        {"title": "너무 오래된 매물 기사", "url": "https://x/3", "channel": "네이버", "brand": "직방",
         "snippet": "", "collected_at": "2026-06-01 10:00:00"},
    ]
    monkeypatch.setattr(agent_chat.cached_db, "get_mentions", lambda brand, limit: mentions)

    result = agent_chat.search_mentions(keyword="매물", brand="직방", days=30, limit=5)

    assert [r["url"] for r in result] == ["https://x/1"]


def test_search_mentions_returns_most_recent_first_capped_at_limit(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 8, 20, 12, 0, 0))
    mentions = [
        {"title": f"기사{i}", "url": f"https://x/{i}", "channel": "네이버", "brand": "직방",
         "snippet": "", "collected_at": f"2026-08-{10 + i:02d} 10:00:00"}
        for i in range(5)
    ]
    monkeypatch.setattr(agent_chat.cached_db, "get_mentions", lambda brand, limit: mentions)

    result = agent_chat.search_mentions(brand="직방", limit=2)

    assert [r["url"] for r in result] == ["https://x/4", "https://x/3"]


def test_search_mentions_returns_empty_list_when_nothing_matches(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 8, 20, 12, 0, 0))
    monkeypatch.setattr(agent_chat.cached_db, "get_mentions", lambda brand, limit: [])

    assert agent_chat.search_mentions(keyword="없는키워드") == []


def test_get_brand_mention_trend_aggregates_counts_per_date(monkeypatch):
    mentions = [
        {"brand": "직방", "collected_at": "2026-08-10 09:00:00"},
        {"brand": "직방", "collected_at": "2026-08-10 15:00:00"},
        {"brand": "직방", "collected_at": "2026-08-11 09:00:00"},
        {"brand": "다방", "collected_at": "2026-08-11 09:00:00"},
    ]
    monkeypatch.setattr(agent_chat.cached_db, "get_mentions_since", lambda days: mentions)

    result = agent_chat.get_brand_mention_trend("직방", days=30)

    assert result == [{"date": "2026-08-10", "count": 2}, {"date": "2026-08-11", "count": 1}]


def test_get_brand_mention_trend_returns_empty_list_for_untracked_brand(monkeypatch):
    monkeypatch.setattr(agent_chat.cached_db, "get_mentions_since", lambda days: [
        {"brand": "다방", "collected_at": "2026-08-11 09:00:00"},
    ])

    assert agent_chat.get_brand_mention_trend("없는브랜드", days=30) == []


def test_get_trending_brands_ranks_by_spike_ratio(monkeypatch):
    def fake_top(days, limit):
        if days == 3:
            return [{"brand": "직방", "count": 9}, {"brand": "다방", "count": 3}]
        return [{"brand": "직방", "count": 12}, {"brand": "다방", "count": 30}]  # baseline=30일

    monkeypatch.setattr(agent_chat.cached_db, "get_top_mentioned_brands", fake_top)

    result = agent_chat.get_trending_brands(recent_days=3, baseline_days=30, limit=5)

    # 직방: 최근 3일 9건(일평균 3) vs 그 이전 27일 3건(일평균 0.11) → 급증
    # 다방: 최근 3일 3건(일평균 1) vs 그 이전 27일 27건(일평균 1) → 평소 수준
    assert result[0]["brand"] == "직방"
    assert result[0]["spike_ratio"] > result[1]["spike_ratio"]


def test_get_trending_brands_treats_zero_baseline_as_new_activity(monkeypatch):
    monkeypatch.setattr(
        agent_chat.cached_db, "get_top_mentioned_brands",
        lambda days, limit: [{"brand": "신규브랜드", "count": 6}] if days == 3 else [{"brand": "신규브랜드", "count": 6}],
    )

    result = agent_chat.get_trending_brands(recent_days=3, baseline_days=30, limit=5)

    assert result[0]["brand"] == "신규브랜드"
    assert result[0]["baseline_daily_avg"] == 0.0
    assert result[0]["spike_ratio"] > 0


def test_stats_tools_include_graph_queries_tools():
    import graph_queries

    assert graph_queries.category_alignment_counts in agent_chat._STATS_TOOLS
    assert graph_queries.policy_event_mention_impact in agent_chat._STATS_TOOLS
    assert graph_queries.brand_role_category_breakdown in agent_chat._STATS_TOOLS
