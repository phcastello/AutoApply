"""Protocol, credential boundaries and diagnostics of the shared AI path."""

import json
import time
from unittest.mock import Mock

import pytest

from config.ai_destination import destination
from config.settings import LLMConfig, environment_credential
from core import ai_engine as ai
from core.ai_configuration import public_llm, resolve_draft


def response(status=200, data=None):
    r = Mock(status_code=status, headers={"x-request-id": "req_fixture"})
    r.json.return_value = (
        data
        if data is not None
        else {
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": []},
                {"type": "message", "content": [{"type": "output_text", "text": "OK"}]},
            ],
        }
    )
    return r


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "DEEPSEEK_API_KEY",
        "AUTOAPPLY_LLM_API_KEY",
        "AUTOAPPLY_LLM_PROVIDER",
        "AUTOAPPLY_LLM_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("config.settings._check_keyring", lambda: False)


def test_sol_request_and_response(monkeypatch):
    post = Mock(return_value=response())
    monkeypatch.setattr(ai.requests, "post", post)
    llm = LLMConfig(provider="openai", model="gpt-6.1-sol", api_key="fixture-secret")
    result = ai.test_configuration(llm)
    assert result["valid"] and result["model"] == "gpt-6.1-sol"
    (url,) = post.call_args.args
    body = post.call_args.kwargs["json"]
    assert url == "https://api.openai.com/v1/responses"
    assert body["max_output_tokens"] == 4096 and body["reasoning"] == {"effort": "low"}
    assert body["store"] is False
    assert not {"messages", "max_tokens", "temperature", "service_tier"} & body.keys()
    assert "fixture-secret" not in json.dumps(result)
    assert post.call_count == 1 and post.call_args.kwargs["allow_redirects"] is False


def test_legacy_official_chat_uses_correct_parameters(monkeypatch):
    post = Mock(return_value=response(data={"choices": [{"message": {"content": "OK"}}]}))
    monkeypatch.setattr(ai.requests, "post", post)
    llm = LLMConfig(
        provider="openai",
        model="gpt-6.1-sol",
        api_key="fixture",
        endpoint="https://api.openai.com/v1/chat/completions",
    )
    assert ai.test_configuration(llm)["valid"]
    body = post.call_args.kwargs["json"]
    assert body["max_completion_tokens"] == 4096
    assert "max_tokens" not in body and "input" not in body


def test_compatible_chat_keeps_vendor_parameters(monkeypatch):
    post = Mock(return_value=response(data={"choices": [{"message": {"content": "OK"}}]}))
    monkeypatch.setattr(ai.requests, "post", post)
    llm = LLMConfig(provider="compatible", endpoint="http://localhost:11434/v1", model="new-model")
    assert ai.test_configuration(llm)["valid"]
    assert post.call_args.args[0] == "http://localhost:11434/v1/chat/completions"
    assert post.call_args.kwargs["json"]["max_tokens"] == 4096
    assert "Authorization" not in post.call_args.kwargs["headers"]


@pytest.mark.parametrize(
    "status,code,category",
    [
        (401, "invalid_api_key", "authentication"),
        (403, "permission_denied", "permission"),
        (404, "model_not_found", "model_unavailable"),
        (400, "unsupported_parameter", "request"),
        (429, "insufficient_quota", "quota"),
        (429, "rate_limit_exceeded", "rate_limit"),
        (503, None, "provider"),
        (302, None, "endpoint"),
    ],
)
def test_safe_structured_error(monkeypatch, status, code, category):
    post = Mock(
        return_value=response(
            status,
            {
                "error": {
                    "code": code,
                    "param": "max_tokens",
                    "message": "fixture-secret private-personal-data http://secret-url.invalid",
                }
            },
        )
    )
    monkeypatch.setattr(ai.requests, "post", post)
    result = ai.test_configuration(
        LLMConfig(provider="openai", api_key="fixture-secret", model="gpt-6.1-sol")
    )
    assert result["valid"] is False
    assert result["error"]["category"] == category
    assert result["error"]["http_status"] == status
    assert result["error"]["code"] == code
    assert result["error"]["request_id"] == "req_fixture"
    assert "fixture-secret" not in json.dumps(result) and "private-personal-data" not in json.dumps(
        result
    )
    assert post.call_count == 1


@pytest.mark.parametrize(
    "payload,category",
    [
        (
            {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}},
            "output_limit",
        ),
        ({"output": []}, "empty_response"),
        (
            {
                "output": [
                    {"type": "message", "content": [{"type": "refusal", "refusal": "private"}]}
                ]
            },
            "refusal",
        ),
    ],
)
def test_no_false_positive_on_missing_generation(monkeypatch, payload, category):
    monkeypatch.setattr(ai.requests, "post", Mock(return_value=response(data=payload)))
    assert (
        ai.test_configuration(LLMConfig(provider="openai", api_key="fixture"))["error"]["category"]
        == category
    )


def test_finite_total_timeout(monkeypatch):
    def slow(*a, **k):
        time.sleep(0.2)
        return response()

    monkeypatch.setattr(ai.requests, "post", slow)
    start = time.monotonic()
    with pytest.raises(ai.AIError) as error:
        ai.invoke_llm("OK", LLMConfig(provider="openai", api_key="fixture"), timeout_seconds=0.03)
    assert error.value.details["category"] == "timeout" and time.monotonic() - start < 0.15


def test_future_model_id_not_blocked(monkeypatch):
    post = Mock(return_value=response())
    monkeypatch.setattr(ai.requests, "post", post)
    assert ai.test_configuration(
        LLMConfig(provider="openai", model="gpt-future-model", api_key="fixture")
    )["valid"]
    assert "reasoning" not in post.call_args.kwargs["json"]


def test_draft_credentials_are_destination_bound():
    existing = LLMConfig(provider="openai", api_key="fixture-secret", model="gpt-6.1-sol")
    assert (
        resolve_draft({"api_key": "", "model": "new-model"}, existing).api_key == "fixture-secret"
    )
    assert resolve_draft({"provider": "deepseek"}, existing).api_key == ""
    assert resolve_draft({"endpoint": "https://example.invalid/v1"}, existing).api_key == ""
    assert (
        resolve_draft({"endpoint": "https://api.openai.com/v1/responses"}, existing).api_key
        == "fixture-secret"
    )
    with pytest.raises(ValueError):
        resolve_draft({"provider": "deepseek", "api_key": "fixture-secret"}, existing)
    with pytest.raises(ValueError):
        resolve_draft({"api_key": "********"}, existing)


def test_provider_environment_does_not_leak(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-fixture")
    official = LLMConfig(provider="openai")
    assert public_llm(official)["has_api_key"]
    assert public_llm(official)["credential_source"] == "environment"
    assert environment_credential(LLMConfig(provider="deepseek")) == ("", "")
    assert environment_credential(
        LLMConfig(provider="openai", endpoint="https://elsewhere.invalid/v1")
    ) == ("", "")
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("AUTOAPPLY_LLM_API_KEY", "legacy-env")
    assert not public_llm(official)["has_api_key"]
    monkeypatch.setenv("AUTOAPPLY_LLM_PROVIDER", "openai")
    assert public_llm(official)["has_api_key"]


@pytest.mark.parametrize(
    "endpoint,protocol,expected",
    [
        ("https://api.openai.com/v1", "auto", "https://api.openai.com/v1/responses"),
        ("https://server.invalid/v1/", "responses", "https://server.invalid/v1/responses"),
        (
            "https://server.invalid/v1/chat/completions",
            "auto",
            "https://server.invalid/v1/chat/completions",
        ),
    ],
)
def test_endpoint_canonicalization(endpoint, protocol, expected):
    assert destination("openai", endpoint, protocol)[0] == expected


def test_both_http_validators_use_unsaved_selection(tmp_path, monkeypatch):
    from app import app

    monkeypatch.setenv("AUTOAPPLY_DATA_DIR", str(tmp_path))
    post = Mock(return_value=response())
    monkeypatch.setattr(ai.requests, "post", post)
    client = app.test_client()
    draft = {"provider": "openai", "model": "gpt-6.1-sol", "api_key": "fixture-secret"}
    for route in ("/api/ai/validate", "/api/assistant/ai/test"):
        result = client.post(route, json=draft)
        assert result.status_code == 200 and result.json["valid"]
        assert post.call_args.kwargs["json"]["model"] == draft["model"]
    assert not (tmp_path / "config.json").exists()


def test_legacy_vault_migration_and_removal_do_not_resurrect_key(tmp_path, monkeypatch):
    import keyring

    from config.settings import (
        KEYRING_KEY_NAME,
        AppConfig,
        load_config,
        remove_credential,
        save_config,
    )

    monkeypatch.setenv("AUTOAPPLY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("config.settings._check_keyring", lambda: True)
    vault = {f"{KEYRING_KEY_NAME}:openai:default": "fixture-old-secret"}
    monkeypatch.setattr(keyring, "get_password", lambda service, name: vault.get(name))
    monkeypatch.setattr(
        keyring, "set_password", lambda service, name, value: vault.update({name: value})
    )

    def delete(service, name):
        if name not in vault:
            raise keyring.errors.PasswordDeleteError()
        del vault[name]

    monkeypatch.setattr(keyring, "delete_password", delete)
    config = AppConfig(
        profile=dict(first_name="", last_name="", email="", phone="", city="", state="", bio=""),
        search_criteria=dict(job_titles=[], locations=[]),
        llm=dict(provider="openai"),
    )
    legacy = config.model_dump()
    del legacy["llm"]["credential_version"]
    (tmp_path / "config.json").write_text(json.dumps(legacy), encoding="utf-8")
    loaded = load_config()
    assert loaded.llm.api_key == "fixture-old-secret"
    loaded.llm.endpoint = "https://api.openai.com/v1/responses"
    remove_credential(loaded.llm)
    save_config(loaded)
    assert load_config().llm.api_key == ""
    loaded.llm.endpoint = ""
    save_config(loaded)
    assert load_config().llm.api_key == ""


def test_environment_metadata_agrees_in_both_configuration_apis(tmp_path, monkeypatch):
    from app import app
    from config.settings import AppConfig, save_config

    monkeypatch.setenv("AUTOAPPLY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-env-secret")
    config = AppConfig(
        profile=dict(first_name="", last_name="", email="", phone="", city="", state="", bio=""),
        search_criteria=dict(job_titles=[], locations=[]),
        llm=dict(provider="openai"),
    )
    save_config(config)
    for route in ("/api/config", "/api/assistant/config"):
        result = app.test_client().get(route)
        assert (
            result.json["llm"]["has_api_key"]
            and result.json["llm"]["credential_source"] == "environment"
        )
        assert "fixture-env-secret" not in result.get_data(as_text=True)
