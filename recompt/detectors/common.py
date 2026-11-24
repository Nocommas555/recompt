import re
from pathlib import Path

from recompt.models import Requirement, Source, Step

VERSION = re.compile(r"\d+(?:\.\d+)*")


def min_version(spec: str | None) -> str | None:
    if not spec:
        return None
    match = VERSION.search(spec)
    return match.group(0) if match else None


def root(copy) -> Path:
    return Path(copy.path)


def req(tool: str, origin: str, version: str | None = None) -> Requirement:
    return Requirement(tool=tool, min_version=version, source=Source.BUILD_FILE, origin=origin)


def step(kind: str, command, origin: str, shell: str = "exec") -> Step:
    return Step(kind=kind, command=command, shell=shell, source=Source.BUILD_FILE, origin=origin)


def exe(name: str, host_os: str) -> str:
    return f"{name}.exe" if host_os == "windows" else name
