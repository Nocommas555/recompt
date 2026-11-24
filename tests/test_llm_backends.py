import sys
from types import SimpleNamespace

import anthropic
import ollama
import pytest
from pydantic import ValidationError

from recompt.config import LLMConfig
from recompt.llm import select_backend
from recompt.llm.base import DocSection, LLMUnavailable
from recompt.llm.claude import ClaudeBackend
from recompt.llm.ollama import OllamaBackend
from recompt.models import ExtractedPlan, ExtractedStep

SECTIONS = [DocSection(file="README.md", heading="Build", text="run `make`")]
PLAN = ExtractedPlan(steps=[ExtractedStep(kind="build", command="make")])


def bare(cls, msg="boom"):
    err = cls.__new__(cls)
    Exception.__init__(err, msg)
    return err


class FakeClaudeMessages:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.kwargs = result, error, None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.result


def claude_with(result=None, error=None):
    messages = FakeClaudeMessages(result, error)
    return ClaudeBackend(model="claude-opus-5-5", client=SimpleNamespace(messages=messages)), messages


def test_claude_calls_parse_with_schema_and_returns_parsed_output():
    backend, messages = claude_with(SimpleNamespace(parsed_output=PLAN, stop_reason="end_turn"))
    assert backend.extract_plan(SECTIONS) == PLAN
    assert messages.kwargs["model"] == "claude-opus-5-5"
    assert messages.kwargs["max_tokens"] == 16000
    assert messages.kwargs["output_format"] is ExtractedPlan
    assert "run `make`" in messages.kwargs["messages"][0]["content"]
    assert "untrusted" in messages.kwargs["system"].lower()


@pytest.mark.parametrize(
    "error",
    [
        bare(anthropic.RateLimitError),
        bare(anthropic.AuthenticationError),
        bare(anthropic.APIStatusError),
        bare(anthropic.APIConnectionError),
    ],
)
def test_claude_api_errors_become_unavailable(error):
    backend, _ = claude_with(error=error)
    with pytest.raises(LLMUnavailable):
        backend.extract_plan(SECTIONS)


def test_claude_missing_credentials_type_error_is_unavailable():
    backend, _ = claude_with(error=TypeError('"Could not resolve authentication method. Expected one of api_key"'))
    with pytest.raises(LLMUnavailable) as exc:
        backend.extract_plan(SECTIONS)
    assert "credentials" in str(exc.value)


def test_claude_other_type_errors_are_not_swallowed():
    backend, _ = claude_with(error=TypeError("unexpected keyword argument"))
    with pytest.raises(TypeError):
        backend.extract_plan(SECTIONS)


def test_claude_refusal_or_empty_output_is_unavailable():
    backend, _ = claude_with(SimpleNamespace(parsed_output=None, stop_reason="refusal"))
    with pytest.raises(LLMUnavailable):
        backend.extract_plan(SECTIONS)


def test_claude_missing_package_is_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(LLMUnavailable) as exc:
        ClaudeBackend(model="m").extract_plan(SECTIONS)
    assert "recompt[claude]" in str(exc.value)


class FakeOllama:
    def __init__(self, content=None, error=None):
        self.content, self.error, self.kwargs = content, error, None

    def chat(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(message=SimpleNamespace(content=self.content))


def test_ollama_calls_chat_with_schema_and_validates():
    client = FakeOllama(content=PLAN.model_dump_json())
    backend = OllamaBackend(model="llama3.1:8b", client=client)
    assert backend.extract_plan(SECTIONS) == PLAN
    assert client.kwargs["model"] == "llama3.1:8b"
    assert client.kwargs["format"] == ExtractedPlan.model_json_schema()
    assert client.kwargs["options"] == {"temperature": 0}


@pytest.mark.parametrize(
    "client",
    [
        FakeOllama(error=ollama.ResponseError("model not found", 404)),
        FakeOllama(error=ConnectionError("Failed to connect to Ollama")),
        FakeOllama(content='{"steps": [{"kind": "nonsense", "command": 1}]}'),
        FakeOllama(content="not json"),
    ],
)
def test_ollama_errors_become_unavailable(client):
    with pytest.raises(LLMUnavailable):
        OllamaBackend(model="m", client=client).extract_plan(SECTIONS)


def test_ollama_missing_package_is_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "ollama", None)
    with pytest.raises(LLMUnavailable) as exc:
        OllamaBackend(model="m").extract_plan(SECTIONS)
    assert "recompt[ollama]" in str(exc.value)


def cfg(backend):
    return LLMConfig(backend=backend)


def test_selection_explicit_choices():
    assert select_backend(cfg("none")) is None
    assert isinstance(select_backend(cfg("claude")), ClaudeBackend)
    assert isinstance(select_backend(cfg("ollama")), OllamaBackend)
    assert select_backend(cfg("claude")).model == "claude-opus-5-5"
    assert select_backend(cfg("ollama")).model == "llama3.1:8b"


@pytest.mark.parametrize(
    "claude_ok, ollama_ok, expected",
    [(True, True, ClaudeBackend), (False, True, OllamaBackend), (False, False, type(None))],
)
def test_selection_auto_order(claude_ok, ollama_ok, expected):
    chosen = select_backend(
        cfg("auto"), has_claude_credentials=lambda: claude_ok, ollama_reachable=lambda: ollama_ok
    )
    assert isinstance(chosen, expected)


def test_validation_error_is_a_pydantic_error():
    with pytest.raises(ValidationError):
        ExtractedPlan.model_validate_json('{"steps": [{"kind": "x", "command": "y"}]}')
