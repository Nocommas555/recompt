import json
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "fixtures"))

from readme_cases import CASES, FORBIDDEN  # noqa: E402

from recompt.config import LLMConfig  # noqa: E402
from recompt.detectors.readme import detect  # noqa: E402
from recompt.llm import claude_credentials_present, ollama_server_reachable  # noqa: E402
from recompt.llm.claude import ClaudeBackend  # noqa: E402
from recompt.llm.ollama import OllamaBackend  # noqa: E402
from recompt.models import DetectContext, WorkingCopy  # noqa: E402

pytestmark = pytest.mark.llm


def ollama_model() -> str:
    default = LLMConfig().ollama_model
    with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as resp:
        names = [m["name"] for m in json.load(resp)["models"]]
    return default if default in names else names[0]


def backends():
    found = []
    if claude_credentials_present():
        found.append(pytest.param(lambda: ClaudeBackend(model=LLMConfig().claude_model), id="claude"))
    if ollama_server_reachable():
        found.append(pytest.param(lambda: OllamaBackend(model=ollama_model()), id="ollama"))
    return found or [pytest.param(None, marks=pytest.mark.skip(reason="no LLM backend available"))]


def squash(text: str) -> str:
    return " ".join(text.split())


@pytest.mark.parametrize("make_backend", backends())
@pytest.mark.parametrize("case", sorted(CASES))
def test_backend_extracts_expected_commands(tmp_path, make_backend, case):
    readme, expected = CASES[case]
    (tmp_path / "README.md").write_text(readme)
    copy = WorkingCopy(path=str(tmp_path), in_place=True)
    [finding] = detect(copy, DetectContext(host_os="linux", llm=make_backend()))
    assert finding.steps, finding.notes
    extracted = squash(" \n ".join(s.command for s in finding.steps))
    for command in expected:
        assert squash(command) in extracted, f"missing {command!r} in {extracted!r}"
    for bad in FORBIDDEN.get(case, []):
        assert bad not in extracted
    assert all(s.needs_confirm for s in finding.steps)
