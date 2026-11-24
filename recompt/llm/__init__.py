import importlib.util
import os
import urllib.request
from pathlib import Path
from typing import Callable

from recompt.config import LLMConfig
from recompt.llm.base import LLMBackend
from recompt.llm.claude import ClaudeBackend
from recompt.llm.ollama import OllamaBackend

OLLAMA_VERSION_URL = "http://localhost:11434/api/version"


def claude_credentials_present() -> bool:
    if importlib.util.find_spec("anthropic") is None:
        return False
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return (Path.home() / ".config" / "anthropic").is_dir()


def ollama_server_reachable() -> bool:
    if importlib.util.find_spec("ollama") is None:
        return False
    try:
        with urllib.request.urlopen(OLLAMA_VERSION_URL, timeout=1):
            return True
    except OSError:
        return False


def select_backend(
    cfg: LLMConfig,
    *,
    has_claude_credentials: Callable[[], bool] = claude_credentials_present,
    ollama_reachable: Callable[[], bool] = ollama_server_reachable,
) -> LLMBackend | None:
    claude = ClaudeBackend(model=cfg.claude_model)
    local = OllamaBackend(model=cfg.ollama_model)
    if cfg.backend == "claude":
        return claude
    if cfg.backend == "ollama":
        return local
    if cfg.backend == "auto":
        if has_claude_credentials():
            return claude
        if ollama_reachable():
            return local
    return None
