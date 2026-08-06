from unittest.mock import MagicMock, patch

import agent_chat


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
