import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlsplit, urlunsplit

from platformdirs import user_cache_path

from recompt.errors import InvalidInputError
from recompt.models import WorkingCopy

GIT_SCHEMES = ("https://", "http://", "ssh://", "git://", "file://")
SCP_STYLE = re.compile(r"^[\w.-]+@[\w.-]+:.+")
GITHUB_PAGE = re.compile(r"^(https?://github\.com/[^/]+/[^/]+?)(?:\.git)?/(?:tree|blob)/(.+)$")
COMMIT_ID = re.compile(r"^[0-9a-f]{7,40}$")

SHORT_COMMIT_ID = re.compile(r"^[0-9a-f]{7,39}$")
FULL_COMMIT_ID = re.compile(r"^[0-9a-f]{40}$")
URL_CREDENTIALS = re.compile(r"(\w+://)[^/@\s]+@")


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str


LsRemote = Callable[[str], list[str]]
Git = Callable[[list[str], Path], GitResult]


@dataclass(frozen=True)
class NormalizedSource:
    fetch_url: str
    display_url: str
    ref: str | None


def classify(value: str) -> Literal["local", "git"]:
    path = Path(value)
    if path.exists():
        if not path.is_dir():
            raise InvalidInputError(f"{value} is a file, not a folder or a git URL")
        return "local"
    if value.startswith(GIT_SCHEMES) or SCP_STYLE.match(value):
        return "git"
    raise InvalidInputError(f"{value} is not an existing folder or a git URL")


def _display(url: str) -> str:
    url = url.removesuffix("/").removesuffix(".git")
    if SCP_STYLE.match(url) and not url.startswith(GIT_SCHEMES):
        return url
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _resolve_page_ref(rest: str, refs: list[str]) -> str:
    segments = rest.split("/")
    for n in range(len(segments), 0, -1):
        candidate = "/".join(segments[:n])
        if candidate in refs:
            return candidate
    if COMMIT_ID.match(segments[0]):
        return segments[0]
    raise InvalidInputError(f"No branch or tag in the repository matches '{rest}'")


def normalize(url: str, ls_remote: LsRemote) -> NormalizedSource:
    page = GITHUB_PAGE.match(url)
    if page:
        repo, rest = page.group(1), page.group(2)
        ref = _resolve_page_ref(rest, ls_remote(repo))
        return NormalizedSource(fetch_url=repo, display_url=_display(repo), ref=ref)
    return NormalizedSource(fetch_url=url, display_url=_display(url), ref=None)


def cache_path(display_url: str, ref: str | None, base: Path) -> Path:
    key = hashlib.sha256(f"{display_url}#{ref or ''}".encode()).hexdigest()[:16]
    return base / "src" / key


def run_git(args: list[str], cwd: Path) -> GitResult:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return GitResult(proc.returncode, proc.stdout, proc.stderr)


def strip_credentials(text: str) -> str:
    return URL_CREDENTIALS.sub(r"\1", text)


def _clean(text: str) -> str:
    return strip_credentials(text).strip()


def _fetch(src: NormalizedSource, ref: str | None, dest: Path, git: Git) -> None:
    def call(*args: str) -> GitResult:
        return git(list(args), dest)

    def fail(what: str, result: GitResult) -> InvalidInputError:
        return InvalidInputError(f"{what} {src.display_url}: {_clean(result.stderr)}")

    existing = (dest / ".git").exists()
    if not existing:
        dest.mkdir(parents=True, exist_ok=True)
        call("init", "--quiet")
        call("remote", "add", "origin", src.fetch_url)

    target = ref or "HEAD"
    if ref and SHORT_COMMIT_ID.match(ref):
        shallow = None
    else:
        shallow = call("fetch", "--depth", "1", "origin", target)

    if shallow is not None and shallow.returncode == 0:
        done = call("reset", "--quiet", "--hard", "FETCH_HEAD") if existing else call(
            "checkout", "--quiet", "FETCH_HEAD"
        )
        if done.returncode != 0:
            raise fail(f"Cannot check out {target} of", done)
    elif ref and (SHORT_COMMIT_ID.match(ref) or FULL_COMMIT_ID.match(ref)):
        full = call("fetch", "--quiet", "origin")
        if full.returncode != 0:
            raise fail("Cannot fetch", full)
        done = call("checkout", "--quiet", ref)
        if done.returncode != 0:
            raise fail(f"Commit {ref} not found in", done)
    else:
        raise fail(f"Cannot fetch ref '{target}' from", shallow)

    sub = call("submodule", "update", "--init", "--recursive", "--depth", "1")
    if sub.returncode != 0:
        raise fail("Cannot fetch submodules of", sub)


def resolve(
    value: str,
    ref: str | None = None,
    *,
    git: Git = run_git,
    ls_remote: LsRemote | None = None,
    cache_base: Path | None = None,
) -> WorkingCopy:
    if classify(value) == "local":
        return WorkingCopy(path=str(Path(value).resolve()), in_place=True)
    src = normalize(value, ls_remote=ls_remote or git_ls_remote)
    ref = ref or src.ref
    dest = cache_path(src.display_url, ref, cache_base or user_cache_path("recompt"))
    _fetch(src, ref, dest, git)
    return WorkingCopy(path=str(dest), in_place=False, url=src.display_url, ref=ref)


def git_ls_remote(url: str) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-remote", "--heads", "--tags", url], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise InvalidInputError(f"Cannot reach {_display(url)}: {proc.stderr.strip()}")
    refs = []
    for line in proc.stdout.splitlines():
        name = line.split("\t", 1)[-1].removesuffix("^{}")
        for prefix in ("refs/heads/", "refs/tags/"):
            if name.startswith(prefix):
                refs.append(name[len(prefix):])
    return refs
