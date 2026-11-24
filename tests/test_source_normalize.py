import pytest

from recompt.errors import InvalidInputError
from recompt.source import classify, normalize


@pytest.mark.parametrize(
    "value",
    [
        "https://github.com/o/r",
        "http://example.org/r.git",
        "ssh://git@example.org/o/r.git",
        "git://example.org/r.git",
        "file:///srv/repos/r.git",
        "git@github.com:o/r.git",
    ],
)
def test_git_urls_are_classified_as_git(value):
    assert classify(value) == "git"


def test_existing_folder_is_classified_as_local(tmp_path):
    assert classify(str(tmp_path)) == "local"


@pytest.mark.parametrize("value", ["not a thing", "/no/such/folder/here", "ftp://example.org/r"])
def test_anything_else_is_invalid(value):
    with pytest.raises(InvalidInputError) as exc:
        classify(value)
    assert value in exc.value.message


def test_existing_file_is_invalid(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(InvalidInputError):
        classify(str(f))


def no_refs(url):
    raise AssertionError("ls-remote must not be called for plain URLs")


def test_credentials_are_removed_from_display_url_but_kept_for_fetch():
    src = normalize("https://user:token@example.org/o/r.git", ls_remote=no_refs)
    assert src.display_url == "https://example.org/o/r"
    assert "token" not in src.display_url
    assert src.fetch_url == "https://user:token@example.org/o/r.git"
    assert src.ref is None


def test_git_suffix_is_optional_for_display_url():
    a = normalize("https://example.org/o/r.git", ls_remote=no_refs)
    b = normalize("https://example.org/o/r", ls_remote=no_refs)
    assert a.display_url == b.display_url


def test_scp_style_url_is_kept():
    src = normalize("git@github.com:o/r.git", ls_remote=no_refs)
    assert src.fetch_url == "git@github.com:o/r.git"
    assert src.display_url == "git@github.com:o/r"


REFS = ["main", "feature/x", "feature", "v1.0"]


@pytest.mark.parametrize(
    "url, ref",
    [
        ("https://github.com/o/r/tree/main", "main"),
        ("https://github.com/o/r/tree/main/src/lib", "main"),
        ("https://github.com/o/r/tree/feature/x/docs", "feature/x"),
        ("https://github.com/o/r/blob/v1.0/README.md", "v1.0"),
        ("https://github.com/o/r/tree/feature", "feature"),
    ],
)
def test_github_page_urls_resolve_repo_and_longest_matching_ref(url, ref):
    calls = []

    def ls_remote(repo_url):
        calls.append(repo_url)
        return REFS

    src = normalize(url, ls_remote=ls_remote)
    assert src.fetch_url == "https://github.com/o/r"
    assert src.display_url == "https://github.com/o/r"
    assert src.ref == ref
    assert calls == ["https://github.com/o/r"]


def test_github_page_url_with_commit_id_uses_it_as_ref():
    sha = "0123456789abcdef0123456789abcdef01234567"
    src = normalize(f"https://github.com/o/r/blob/{sha}/x.c", ls_remote=lambda u: REFS)
    assert src.ref == sha


def test_github_page_url_with_unknown_ref_is_invalid():
    with pytest.raises(InvalidInputError):
        normalize("https://github.com/o/r/tree/nope/src", ls_remote=lambda u: REFS)
