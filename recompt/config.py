import tomllib
from pathlib import Path
from typing import Literal

from platformdirs import user_config_path
from pydantic import BaseModel, Field, ValidationError

from recompt.errors import InvalidInputError


class LLMConfig(BaseModel):
    backend: Literal["auto", "claude", "ollama", "none"] = "auto"
    claude_model: str = "claude-opus-5-5"
    ollama_model: str = "llama3.1:8b"


class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    step_timeout: int = Field(default=1800, gt=0)


def default_config_path() -> Path:
    return user_config_path("recompt") / "config.toml"


def load_config(path: Path | None = None) -> Config:
    path = path or default_config_path()
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text())
        return Config.model_validate(data)
    except (tomllib.TOMLDecodeError, ValidationError) as exc:
        raise InvalidInputError(f"Invalid config file {path}: {exc}") from exc
