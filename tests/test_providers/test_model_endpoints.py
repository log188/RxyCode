"""Canonical API-root normalization for all LLM transports."""

from __future__ import annotations

import pytest
from uuid import uuid4

from config.model_endpoint import (
    detect_explicit_transport,
    llm_client_base_url,
    llm_endpoint_url,
    normalize_llm_endpoint,
)


@pytest.mark.parametrize(
    ("base_url", "transport", "root", "endpoint"),
    [
        (
            "https://provider.example/v1/chat",
            "openai_chat",
            "https://provider.example/v1",
            "https://provider.example/v1/chat/completions",
        ),
        (
            "https://provider.example/v1/chat/completions/",
            "openai_chat",
            "https://provider.example/v1",
            "https://provider.example/v1/chat/completions",
        ),
        (
            "https://provider.example/v1/responses",
            "openai_responses",
            "https://provider.example/v1",
            "https://provider.example/v1/responses",
        ),
        (
            "https://provider.example/v1/messages",
            "anthropic_messages",
            "https://provider.example/v1",
            "https://provider.example/v1/messages",
        ),
        (
            "https://opencode.ai/zen/go/v1/responses",
            "openai_responses",
            "https://opencode.ai/zen/go/v1",
            "https://opencode.ai/zen/go/v1/responses",
        ),
        (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/responses/",
            "openai_responses",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/responses",
        ),
    ],
)
def test_normalization_removes_only_the_matching_terminal_resource(
    base_url, transport, root, endpoint
):
    assert normalize_llm_endpoint(base_url, transport) == root
    assert llm_endpoint_url(base_url, transport) == endpoint


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://provider.example/v1/CHAT/COMPLETIONS/", "openai_chat"),
        ("https://provider.example/v1/Responses", "openai_responses"),
        ("https://provider.example/v1/Messages/", "anthropic_messages"),
        ("https://provider.example/v1/myresponses", None),
        ("https://provider.example/v1/chatty", None),
    ],
)
def test_explicit_resource_detection_is_case_insensitive_and_exact(
    base_url, expected
):
    assert detect_explicit_transport(base_url) == expected


@pytest.mark.parametrize(
    ("base_url", "transport"),
    [
        ("https://provider.example/v1/responses", "openai_chat"),
        ("https://provider.example/v1/messages", "openai_responses"),
        ("https://provider.example/v1/chat/completions", "anthropic_messages"),
    ],
)
def test_explicit_resource_conflict_fails_before_network(base_url, transport):
    with pytest.raises(ValueError, match="conflicts"):
        normalize_llm_endpoint(base_url, transport)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://user@provider.example/v1",
        "https://provider.example/v1?mode=test",
        "https://provider.example/v1#fragment",
        "https://provider.example:bad/v1",
        "https://provider.example/v1 with-space",
    ],
)
def test_unsafe_or_ambiguous_urls_are_rejected(base_url):
    with pytest.raises(ValueError, match="base_url"):
        normalize_llm_endpoint(base_url, "openai_chat")


def test_plain_http_is_rejected_when_a_credential_will_be_sent():
    with pytest.raises(ValueError, match="https"):
        normalize_llm_endpoint(
            "http://provider.example/v1",
            "openai_chat",
            require_https=True,
        )


def test_anthropic_sdk_receives_service_root_but_config_keeps_api_root():
    api_root = "https://provider.example/gateway/v1/messages"
    assert normalize_llm_endpoint(api_root, "anthropic_messages") == (
        "https://provider.example/gateway/v1"
    )
    assert llm_client_base_url(api_root, "anthropic_messages") == (
        "https://provider.example/gateway"
    )


def test_similar_suffix_is_preserved_as_part_of_the_api_root():
    base_url = "https://provider.example/gateway/responses-v2"
    assert normalize_llm_endpoint(base_url, "openai_responses") == base_url
    assert llm_endpoint_url(base_url, "openai_responses") == (
        "https://provider.example/gateway/responses-v2/responses"
    )


@pytest.mark.parametrize(
    ("base_url", "expected_url", "expected_transport", "payload"),
    [
        (
            "https://provider.example/v1/responses",
            "https://provider.example/v1/responses",
            "openai_responses",
            {"output_text": "OK"},
        ),
        (
            "https://provider.example/v1/chat/completions",
            "https://provider.example/v1/chat/completions",
            "openai_chat",
            {"choices": [{"message": {"content": "OK"}}]},
        ),
    ],
)
def test_custom_probe_does_not_duplicate_an_explicit_resource(
    monkeypatch, base_url, expected_url, expected_transport, payload
):
    from config import model_manager

    observed: list[str] = []

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, *, json, headers):
            del json, headers
            observed.append(url)
            return Response()

    monkeypatch.setattr(model_manager.httpx, "Client", Client)
    credential = "test-" + uuid4().hex
    result = model_manager.probe_model_connection(
        api_key=credential,
        base_url=base_url,
        provider_model_id="provider/model",
    )

    assert result["success"] is True
    assert result["transport"] == expected_transport
    assert observed == [expected_url]


def test_anthropic_probe_uses_native_messages_auth_and_validates_reply(monkeypatch):
    from config import model_manager

    observed: dict = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "id": "msg_probe",
                "content": [{"type": "text", "text": "ANTHROPIC_OK"}],
            }

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, *, json, headers):
            observed.update(url=url, json=json, headers=headers)
            return Response()

    monkeypatch.setattr(model_manager.httpx, "Client", Client)
    credential = "test-" + uuid4().hex
    result = model_manager.probe_model_connection(
        api_key=credential,
        base_url="https://api.anthropic.com/v1",
        provider_model_id="claude-haiku-4-5",
    )

    assert result["success"] is True
    assert result["transport"] == "anthropic_messages"
    assert result["reply"] == "ANTHROPIC_OK"
    assert observed["url"] == "https://api.anthropic.com/v1/messages"
    assert observed["json"]["messages"] == [
        {"role": "user", "content": "Hi"}
    ]
    assert observed["headers"]["x-api-key"] == credential
    assert observed["headers"]["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in observed["headers"]


@pytest.mark.parametrize(
    ("base_url", "payload"),
    [
        ("https://provider.example/v1", {"id": "resp_missing_output"}),
        ("https://provider.example/v1/chat", {"id": "chat_missing_choices"}),
    ],
)
def test_probe_rejects_http_200_without_transport_reply_body(
    monkeypatch, base_url, payload
):
    from config import model_manager

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, _url, *, json, headers):
            del json, headers
            return Response()

    monkeypatch.setattr(model_manager.httpx, "Client", Client)
    result = model_manager.probe_model_connection(
        api_key="test-" + uuid4().hex,
        base_url=base_url,
        provider_model_id="provider/model",
    )

    assert result["success"] is False
    assert "no valid" in result["error"]


def test_add_model_persists_api_root_and_explicit_transport(monkeypatch):
    from config import model_manager

    config = {"models": {}}
    saved: list[dict] = []
    monkeypatch.setattr(model_manager, "load_config", lambda: config)
    monkeypatch.setattr(model_manager, "save_config", lambda value: saved.append(value))
    monkeypatch.setattr(
        model_manager,
        "_credential_config",
        lambda _value: {"api_key_env": "RXYCODE_TEST_ENDPOINT_KEY"},
    )

    entry = model_manager.add_model(
        "custom/model",
        "test-" + uuid4().hex,
        "https://provider.example/gateway/v1/responses",
        model_name="custom/model",
        provider_id="custom",
        provider_name="Other",
    )

    assert entry["base_url"] == "https://provider.example/gateway/v1"
    assert entry["api_transport"] == "openai_responses"
    assert "api_key" not in entry
    assert saved == [config]


def test_batch_probe_preserves_explicit_resource_policy(monkeypatch):
    from config import model_manager

    probes: list[str] = []
    additions: list[dict] = []
    monkeypatch.setattr(model_manager, "load_config", lambda: {"models": {}})
    monkeypatch.setattr(
        model_manager,
        "resolve_provider_meta",
        lambda *_args, **_kwargs: {"id": "custom", "name": "Other"},
    )
    monkeypatch.setattr(
        model_manager,
        "probe_model_connection",
        lambda **kwargs: probes.append(kwargs["base_url"]) or {"success": True},
    )
    def add_model(name, api_key, base_url, **kwargs):
        del api_key
        addition = {"name": name, "base_url": base_url, **kwargs}
        additions.append(addition)
        return addition

    monkeypatch.setattr(model_manager, "add_model", add_model)
    monkeypatch.setattr(model_manager, "set_active_model", lambda _name: None)

    result = model_manager.onboard_models_batch(
        api_key="test-" + uuid4().hex,
        base_url="https://provider.example/gateway/v1/chat/completions",
        model_ids=["provider/model"],
        provider_id="custom",
        provider_name="Other",
        skip_probe=False,
    )

    assert result["added"] == ["custom/provider/model"]
    assert probes == ["https://provider.example/gateway/v1/chat/completions"]
    assert additions[0]["base_url"] == "https://provider.example/gateway/v1"
    assert additions[0]["api_transport"] == "openai_chat"
