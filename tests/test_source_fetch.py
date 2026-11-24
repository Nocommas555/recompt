from pathlib import Path

import pytest

from recompt.errors import InvalidInputError
from recompt.source import GitResult, cache_path, resolve


def test_cache_path_is_stable_per_url_and_ref(tmp_path):
    a = cache_path("https://example.org/o/r", "main", tmp_path)
    b = cache_path("https://example.org/o/r", "main", tmp_path)
    c = cache_path("https://example.org/o/r", "v1", tmp_path)
    assert a == b
    assert a != c
    assert a.parent == tmp_path / "src"


def test_cache_path_never_contains_credentials(tmp_path):
    p = cache_path("https://example.org/o/r", None, tmp_path)
    assert "token" not in str(p) and "example.org" not in str(p)


class FakeGit:
    def __init__(self, fail=None):
        self.calls: list[list[str]] = []
        self.fail = fail or (lambda args: None)

    def __call__(self, args, cwd):
        self.calls.append(args)
        if args[0] == "init":
            (Path(cwd) / ".git").mkdir(parents=True, exist_ok=True)
        err = self.fail(args)
        if err:
            return GitResult(128, "", err)
        return GitResult(0, "", "")


def run(tmp_path, url="https://example.org/o/r.git", ref=None, git=None):
    git = git or FakeGit()
    copy = resolve(url, ref=ref, git=git, ls_remote=lambda u: [], cache_base=tmp_path)
    return copy, git


def test_new_copy_runs_init_shallow_fetch_checkout_and_submodules(tmp_path):
    copy, git = run(tmp_path, ref="main")
    assert git.calls == [
        ["init", "--quiet"],
        ["remote", "add", "origin", "https://example.org/o/r.git"],
        ["fetch", "--depth", "1", "origin", "main"],
        ["checkout", "--quiet", "FETCH_HEAD"],
        ["submodule", "update", "--init", "--recursive", "--depth", "1"],
    ]
    assert copy.in_place is False
    assert copy.url == "https://example.org/o/r"
    assert copy.ref == "main"
    assert Path(copy.path).parent == tmp_path / "src"


def test_no_ref_fetches_head(tmp_path):
    _, git = run(tmp_path)
    assert ["fetch", "--depth", "1", "origin", "HEAD"] in git.calls


def test_short_commit_id_uses_full_fetch(tmp_path):
    _, git = run(tmp_path, ref="abc1234")
    assert ["fetch", "--quiet", "origin"] in git.calls
    assert ["checkout", "--quiet", "abc1234"] in git.calls
    assert not any(c[:2] == ["fetch", "--depth"] for c in git.calls)


def test_refused_shallow_fetch_of_full_commit_falls_back_to_full_fetch(tmp_path):
    sha = "0123456789abcdef0123456789abcdef01234567"
    git = FakeGit(fail=lambda a: "not our ref" if a[:2] == ["fetch", "--depth"] else None)
    _, git = run(tmp_path, ref=sha, git=git)
    assert ["fetch", "--quiet", "origin"] in git.calls
    assert ["checkout", "--quiet", sha] in git.calls


def test_existing_copy_fetches_and_resets_without_init(tmp_path):
    run(tmp_path, ref="main")
    _, git = run(tmp_path, ref="main")
    assert ["init", "--quiet"] not in git.calls
    assert ["fetch", "--depth", "1", "origin", "main"] in git.calls
    assert ["reset", "--quiet", "--hard", "FETCH_HEAD"] in git.calls


def test_unknown_branch_is_invalid_input_naming_ref(tmp_path):
    git = FakeGit(fail=lambda a: "couldn't find remote ref nope" if a[0] == "fetch" else None)
    with pytest.raises(InvalidInputError) as exc:
        run(tmp_path, ref="nope", git=git)
    assert "nope" in exc.value.message


def test_unreachable_url_is_invalid_input_without_credentials(tmp_path):
    git = FakeGit(fail=lambda a: "Could not resolve host" if a[0] == "fetch" else None)
    with pytest.raises(InvalidInputError) as exc:
        run(tmp_path, url="https://u:secret@nowhere.invalid/r", git=git)
    assert "nowhere.invalid" in exc.value.message
    assert "secret" not in exc.value.message


def test_page_url_ref_is_used_and_explicit_ref_wins(tmp_path):
    git = FakeGit()
    copy = resolve(
        "https://github.com/o/r/tree/dev/src",
        ref=None,
        git=git,
        ls_remote=lambda u: ["dev"],
        cache_base=tmp_path,
    )
    assert copy.ref == "dev"
    copy = resolve(
        "https://github.com/o/r/tree/dev/src",
        ref="main",
        git=FakeGit(),
        ls_remote=lambda u: ["dev"],
        cache_base=tmp_path,
    )
    assert copy.ref == "main"


def test_local_folder_is_used_in_place_and_nothing_runs(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    git = FakeGit()
    copy = resolve(str(project), git=git, ls_remote=lambda u: [], cache_base=tmp_path / "cache")
    assert copy.in_place is True
    assert Path(copy.path) == project.resolve()
    assert copy.url is None
    assert git.calls == []
    assert not (tmp_path / "cache").exists()


def test_missing_folder_is_invalid_input(tmp_path):
    with pytest.raises(InvalidInputError):
        resolve(str(tmp_path / "missing"), git=FakeGit(), ls_remote=lambda u: [], cache_base=tmp_path)
