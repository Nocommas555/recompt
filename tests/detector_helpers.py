from pathlib import Path

from recompt.models import DetectContext, WorkingCopy


def make_project(root: Path, files: dict[str, str]) -> WorkingCopy:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return WorkingCopy(path=str(root), in_place=True)


def ctx(host_os: str = "linux", llm=None) -> DetectContext:
    return DetectContext(host_os=host_os, llm=llm)


def commands(finding) -> list:
    return [s.command for s in finding.steps]
