import subprocess
from pathlib import Path

import pytest

from recompt.source import resolve

pytestmark = pytest.mark.integration

REPO = "https://github.com/pallets/markupsafe"
TAG = "2.1.5"


def head(path: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_clone_at_tag_then_commit_and_reuse(tmp_path):
    by_tag = resolve(REPO, ref=TAG, cache_base=tmp_path)
    assert (Path(by_tag.path) / "setup.py").exists()
    sha = head(by_tag.path)

    by_commit = resolve(REPO, ref=sha, cache_base=tmp_path / "other")
    assert head(by_commit.path) == sha

    again = resolve(REPO, ref=TAG, cache_base=tmp_path)
    assert again.path == by_tag.path
    assert head(again.path) == sha
