import json
from datetime import datetime

from utils import (
    load_channel_visibility,
    load_collection_schedule,
    load_naver_news_collection_schedule,
    load_policy_collection_schedule,
    resolve_relative_korean_date,
    save_channel_visibility,
    save_collection_schedule,
    save_naver_news_collection_schedule,
    save_policy_collection_schedule,
)
import utils


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


def test_load_agent_chat_sessions_defaults_to_empty_list_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "AGENT_CHAT_HISTORY_FILE", tmp_path / "agent_chat_history.json")

    assert utils.load_agent_chat_sessions("192.168.1.1") == []


def test_save_and_load_agent_chat_sessions_roundtrips_for_given_ip(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "AGENT_CHAT_HISTORY_FILE", tmp_path / "agent_chat_history.json")
    sessions = [
        {"started_at": "2026-08-06 09:00", "messages": [{"role": "user", "content": "안녕"}]},
        {"started_at": "2026-08-06 10:00", "messages": [{"role": "assistant", "content": "안녕하세요!"}]},
    ]

    utils.save_agent_chat_sessions("192.168.1.1", sessions)

    assert utils.load_agent_chat_sessions("192.168.1.1") == sessions


def test_agent_chat_sessions_are_isolated_per_ip(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "AGENT_CHAT_HISTORY_FILE", tmp_path / "agent_chat_history.json")
    ip1_sessions = [{"started_at": "", "messages": [{"role": "user", "content": "IP1 메시지"}]}]
    ip2_sessions = [{"started_at": "", "messages": [{"role": "user", "content": "IP2 메시지"}]}]

    utils.save_agent_chat_sessions("192.168.1.1", ip1_sessions)
    utils.save_agent_chat_sessions("192.168.1.2", ip2_sessions)

    assert utils.load_agent_chat_sessions("192.168.1.1") == ip1_sessions
    assert utils.load_agent_chat_sessions("192.168.1.2") == ip2_sessions


def test_load_agent_chat_sessions_returns_empty_list_for_blank_ip(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "AGENT_CHAT_HISTORY_FILE", tmp_path / "agent_chat_history.json")

    assert utils.load_agent_chat_sessions("") == []


def test_save_agent_chat_sessions_does_nothing_for_blank_ip(tmp_path, monkeypatch):
    history_file = tmp_path / "agent_chat_history.json"
    monkeypatch.setattr(utils, "AGENT_CHAT_HISTORY_FILE", history_file)

    utils.save_agent_chat_sessions("", [{"started_at": "", "messages": [{"role": "user", "content": "무시되어야 함"}]}])

    assert not history_file.exists()


def test_load_agent_chat_sessions_migrates_old_flat_message_list_format(tmp_path, monkeypatch):
    """초기 버전은 IP당 메시지 리스트를 그대로 저장했다 — 기존 파일이 남아있어도 깨지지
    않고 진행 중인 대화 하나로 마이그레이션되는지 확인."""
    history_file = tmp_path / "agent_chat_history.json"
    monkeypatch.setattr(utils, "AGENT_CHAT_HISTORY_FILE", history_file)
    old_format = {"192.168.1.1": [{"role": "user", "content": "옛 형식 메시지"}]}
    history_file.write_text(json.dumps(old_format, ensure_ascii=False), encoding="utf-8")

    sessions = utils.load_agent_chat_sessions("192.168.1.1")

    assert len(sessions) == 1
    assert sessions[0]["messages"] == [{"role": "user", "content": "옛 형식 메시지"}]
