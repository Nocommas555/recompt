import os
from dataclasses import dataclass, field
from pathlib import Path

from recompt.errors import NoRunnableOutputError
from recompt.models import BuildPlan

EXCLUDED_NAMES = {".git", "node_modules", ".venv", "venv", "vendor", "__pycache__"}
EXCLUDED_PATHS = ("target/debug", "build/CMakeFiles")
LIBRARY_SUFFIXES = (".so", ".dylib", ".dll", ".a", ".o")


@dataclass
class Collected:
    programs: list[str] = field(default_factory=list)
    launch: list[str] | str | None = None


def _is_program(path: Path, host_os: str) -> bool:
    if host_os == "windows":
        return path.suffix.lower() == ".exe"
    if path.suffix in LIBRARY_SUFFIXES or ".so." in path.name:
        return False
    return os.access(path, os.X_OK)


def _scan(root: Path, since: float, host_os: str) -> list[str]:
    found = []
    for folder, dirs, files in os.walk(root):
        rel = Path(folder).relative_to(root).as_posix()
        dirs[:] = [
            d for d in dirs
            if d not in EXCLUDED_NAMES and f"{rel}/{d}".removeprefix("./") not in EXCLUDED_PATHS
        ]
        for name in files:
            path = Path(folder) / name
            if path.is_file() and not path.is_symlink() and path.stat().st_mtime >= since and _is_program(path, host_os):
                found.append(str(path))
    return sorted(found)


def collect(plan: BuildPlan, workdir: Path, started_at: float, host_os: str) -> Collected:
    workdir = Path(workdir)
    if plan.project_kind == "interpreted":
        launch = next((s.command for s in plan.steps if s.kind == "launch"), None)
        if launch is None:
            raise NoRunnableOutputError("Setup finished, but no way to launch the app was found")
        return Collected(launch=launch)

    expected = [workdir / t.expected_path for t in plan.targets if t.expected_path]
    programs = [str(p) for p in expected if p.is_file()] or _scan(workdir, started_at, host_os)
    if not programs:
        raise NoRunnableOutputError("The build finished, but produced no runnable program")
    return Collected(programs=programs)
