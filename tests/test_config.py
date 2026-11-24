import pytest

from recompt.config import load_config
from recompt.errors import InvalidInputError


def test_defaults_apply_when_no_file_exists(tmp_path):
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg.llm.backend == "auto"
    assert cfg.llm.claude_model == "claude-opus-5-5"
    assert cfg.llm.ollama_model == "llama3.1:8b"
    assert cfg.step_timeout == 1800


def test_file_values_override_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('step_timeout = 60\n[llm]\nbackend = "ollama"\nollama_model = "qwen3:4b"\n')
    cfg = load_config(path)
    assert cfg.step_timeout == 60
    assert cfg.llm.backend == "ollama"
    assert cfg.llm.ollama_model == "qwen3:4b"
    assert cfg.llm.claude_model == "claude-opus-5-5"


@pytest.mark.parametrize(
    "content",
    [
        '[llm]\nbackend = "gpt"\n',
        "step_timeout = -5\n",
        "step_timeout = = broken\n",
    ],
)
def test_invalid_values_raise_invalid_input(tmp_path, content):
    path = tmp_path / "config.toml"
    path.write_text(content)
    with pytest.raises(InvalidInputError):
        load_config(path)


def test_default_path_is_used_when_none_given(tmp_path, monkeypatch):
    monkeypatch.setattr("recompt.config.default_config_path", lambda: tmp_path / "none.toml")
    assert load_config().step_timeout == 1800
