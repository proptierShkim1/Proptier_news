import json
from datetime import datetime

from utils import (
    escape_html,
    load_channel_visibility,
    load_collection_schedule,
    load_mk_news_collection_schedule,
    load_naver_news_collection_schedule,
    load_policy_collection_schedule,
    load_vector_collection_schedule,
    load_webhook_schedule,
    load_webhooks,
    resolve_relative_korean_date,
    save_channel_visibility,
    save_collection_schedule,
    save_mk_news_collection_schedule,
    save_naver_news_collection_schedule,
    save_policy_collection_schedule,
    save_vector_collection_schedule,
    save_webhook_schedule,
)
import utils


def test_escape_html_escapes_script_tags():
    assert escape_html("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_escape_html_escapes_double_quotes():
    assert escape_html('제목 "인용문" 포함') == "제목 &quot;인용문&quot; 포함"


def test_escape_html_escapes_ampersand_before_other_entities():
    assert escape_html("A & B < C") == "A &amp; B &lt; C"


def test_load_policy_collection_schedule_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        utils, "POLICY_COLLECTION_SCHEDULE_FILE", tmp_path / "policy_collection_schedule.json"
    )

    assert load_policy_collection_schedule() == {"times": []}


def test_save_policy_collection_schedule_persists_times(tmp_path, monkeypatch):
    schedule_file = tmp_path / "policy_collection_schedule.json"
    monkeypatch.setattr(utils, "POLICY_COLLECTION_SCHEDULE_FILE", schedule_file)

    save_policy_collection_schedule({"times": ["10:00"]})

    assert json.loads(schedule_file.read_text(encoding="utf-8")) == {"times": ["10:00"]}


def test_policy_collection_schedule_is_independent_of_brand_schedule(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "COLLECTION_SCHEDULE_FILE", tmp_path / "collection_schedule.json")
    monkeypatch.setattr(
        utils, "POLICY_COLLECTION_SCHEDULE_FILE", tmp_path / "policy_collection_schedule.json"
    )

    save_collection_schedule({"times": ["09:00"]})
    save_policy_collection_schedule({"times": ["10:00"]})

    assert load_collection_schedule() == {"times": ["09:00"]}
    assert load_policy_collection_schedule() == {"times": ["10:00"]}


def test_resolve_relative_korean_date_still_works():
    now = datetime(2026, 7, 24, 12, 0, 0)
    assert resolve_relative_korean_date("30분 전", now) == "2026.07.24"


def test_load_naver_news_collection_schedule_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        utils, "NAVER_NEWS_COLLECTION_SCHEDULE_FILE",
        tmp_path / "naver_news_collection_schedule.json",
    )

    assert load_naver_news_collection_schedule() == {"times": []}


def test_save_naver_news_collection_schedule_persists_times(tmp_path, monkeypatch):
    schedule_file = tmp_path / "naver_news_collection_schedule.json"
    monkeypatch.setattr(utils, "NAVER_NEWS_COLLECTION_SCHEDULE_FILE", schedule_file)

    save_naver_news_collection_schedule({"times": ["11:00"]})

    assert json.loads(schedule_file.read_text(encoding="utf-8")) == {"times": ["11:00"]}


def test_naver_news_collection_schedule_is_independent_of_other_schedules(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "COLLECTION_SCHEDULE_FILE", tmp_path / "collection_schedule.json")
    monkeypatch.setattr(
        utils, "POLICY_COLLECTION_SCHEDULE_FILE", tmp_path / "policy_collection_schedule.json"
    )
    monkeypatch.setattr(
        utils, "NAVER_NEWS_COLLECTION_SCHEDULE_FILE", tmp_path / "naver_news_collection_schedule.json"
    )

    save_collection_schedule({"times": ["09:00"]})
    save_policy_collection_schedule({"times": ["10:00"]})
    save_naver_news_collection_schedule({"times": ["11:00"]})

    assert load_collection_schedule() == {"times": ["09:00"]}
    assert load_policy_collection_schedule() == {"times": ["10:00"]}
    assert load_naver_news_collection_schedule() == {"times": ["11:00"]}


def test_load_mk_news_collection_schedule_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        utils, "MK_NEWS_COLLECTION_SCHEDULE_FILE",
        tmp_path / "mk_news_collection_schedule.json",
    )

    assert load_mk_news_collection_schedule() == {"times": []}


def test_save_mk_news_collection_schedule_persists_times(tmp_path, monkeypatch):
    schedule_file = tmp_path / "mk_news_collection_schedule.json"
    monkeypatch.setattr(utils, "MK_NEWS_COLLECTION_SCHEDULE_FILE", schedule_file)

    save_mk_news_collection_schedule({"times": ["11:30"]})

    assert json.loads(schedule_file.read_text(encoding="utf-8")) == {"times": ["11:30"]}


def test_load_vector_collection_schedule_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "VECTOR_COLLECTION_SCHEDULE_FILE", tmp_path / "vector_collection_schedule.json")

    assert load_vector_collection_schedule() == {"times": []}


def test_save_vector_collection_schedule_persists_times(tmp_path, monkeypatch):
    schedule_file = tmp_path / "vector_collection_schedule.json"
    monkeypatch.setattr(utils, "VECTOR_COLLECTION_SCHEDULE_FILE", schedule_file)

    save_vector_collection_schedule({"times": ["12:00"]})

    assert json.loads(schedule_file.read_text(encoding="utf-8")) == {"times": ["12:00"]}


def test_vector_collection_schedule_is_independent_of_other_schedules(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "COLLECTION_SCHEDULE_FILE", tmp_path / "collection_schedule.json")
    monkeypatch.setattr(
        utils, "POLICY_COLLECTION_SCHEDULE_FILE", tmp_path / "policy_collection_schedule.json"
    )
    monkeypatch.setattr(
        utils, "NAVER_NEWS_COLLECTION_SCHEDULE_FILE", tmp_path / "naver_news_collection_schedule.json"
    )
    monkeypatch.setattr(
        utils, "MK_NEWS_COLLECTION_SCHEDULE_FILE", tmp_path / "mk_news_collection_schedule.json"
    )
    monkeypatch.setattr(
        utils, "VECTOR_COLLECTION_SCHEDULE_FILE", tmp_path / "vector_collection_schedule.json"
    )

    save_collection_schedule({"times": ["09:00"]})
    save_policy_collection_schedule({"times": ["10:00"]})
    save_naver_news_collection_schedule({"times": ["11:00"]})
    save_mk_news_collection_schedule({"times": ["11:30"]})
    save_vector_collection_schedule({"times": ["12:00"]})

    assert load_collection_schedule() == {"times": ["09:00"]}
    assert load_policy_collection_schedule() == {"times": ["10:00"]}
    assert load_naver_news_collection_schedule() == {"times": ["11:00"]}
    assert load_mk_news_collection_schedule() == {"times": ["11:30"]}
    assert load_vector_collection_schedule() == {"times": ["12:00"]}


def test_load_channel_visibility_defaults_to_all_channels_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "CHANNEL_VISIBILITY_FILE", tmp_path / "channel_visibility.json")

    assert load_channel_visibility() == utils.ALL_MENTION_CHANNELS


def test_save_channel_visibility_persists_selected_channels(tmp_path, monkeypatch):
    visibility_file = tmp_path / "channel_visibility.json"
    monkeypatch.setattr(utils, "CHANNEL_VISIBILITY_FILE", visibility_file)

    save_channel_visibility(["네이버뉴스API"])

    assert load_channel_visibility() == ["네이버뉴스API"]


def test_load_channel_visibility_ignores_unknown_channel_names(tmp_path, monkeypatch):
    visibility_file = tmp_path / "channel_visibility.json"
    monkeypatch.setattr(utils, "CHANNEL_VISIBILITY_FILE", visibility_file)

    save_channel_visibility(["네이버", "존재하지않는채널"])

    assert load_channel_visibility() == ["네이버"]


def test_load_agent_settings_defaults_to_hybrid_search_off_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "AGENT_SETTINGS_FILE", tmp_path / "agent_settings.json")

    assert utils.load_agent_settings() == {"always_show_hybrid_search": False}


def test_save_and_load_agent_settings_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "AGENT_SETTINGS_FILE", tmp_path / "agent_settings.json")

    utils.save_agent_settings({"always_show_hybrid_search": True})

    assert utils.load_agent_settings() == {"always_show_hybrid_search": True}


def test_load_agent_settings_backfills_missing_key_from_old_file(tmp_path, monkeypatch):
    settings_file = tmp_path / "agent_settings.json"
    monkeypatch.setattr(utils, "AGENT_SETTINGS_FILE", settings_file)
    settings_file.write_text(json.dumps({}), encoding="utf-8")

    assert utils.load_agent_settings() == {"always_show_hybrid_search": False}


# AI AGENT 채팅 기록은 db.py의 agent_chat_messages 테이블(메시지 1건 = 1행)로 옮겨졌다 —
# 이 파일 기반 API 테스트들은 tests/test_db.py의 agent_chat 관련 테스트로 대체되었다.


def test_load_webhooks_defaults_to_empty_list_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "WEBHOOKS_FILE", tmp_path / "webhooks.json")

    assert load_webhooks() == []


def test_add_webhook_appends_entry_with_id_and_enabled_true(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "WEBHOOKS_FILE", tmp_path / "webhooks.json")

    entry = utils.add_webhook("팀채널", "https://example.com/webhook")

    assert entry["name"] == "팀채널"
    assert entry["url"] == "https://example.com/webhook"
    assert entry["enabled"] is True
    assert entry["id"]
    assert load_webhooks() == [entry]


def test_delete_webhook_removes_only_matching_id(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "WEBHOOKS_FILE", tmp_path / "webhooks.json")
    keep = utils.add_webhook("유지", "https://example.com/keep")
    drop = utils.add_webhook("삭제", "https://example.com/drop")

    utils.delete_webhook(drop["id"])

    assert load_webhooks() == [keep]


def test_set_webhook_enabled_toggles_only_matching_webhook(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "WEBHOOKS_FILE", tmp_path / "webhooks.json")
    a = utils.add_webhook("A", "https://example.com/a")
    b = utils.add_webhook("B", "https://example.com/b")

    utils.set_webhook_enabled(a["id"], False)

    webhooks = {w["id"]: w for w in load_webhooks()}
    assert webhooks[a["id"]]["enabled"] is False
    assert webhooks[b["id"]]["enabled"] is True


def test_load_webhook_schedule_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "WEBHOOK_SCHEDULE_FILE", tmp_path / "webhook_schedule.json")

    assert load_webhook_schedule() == {"times": []}


def test_save_webhook_schedule_persists_times(tmp_path, monkeypatch):
    schedule_file = tmp_path / "webhook_schedule.json"
    monkeypatch.setattr(utils, "WEBHOOK_SCHEDULE_FILE", schedule_file)

    save_webhook_schedule({"times": ["09:00", "18:00"]})

    assert json.loads(schedule_file.read_text(encoding="utf-8")) == {"times": ["09:00", "18:00"]}
    assert load_webhook_schedule() == {"times": ["09:00", "18:00"]}
