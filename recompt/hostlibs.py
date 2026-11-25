import posixpath
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from recompt.models import HostLibrary

MOUNT = "/src"
NOT_FOUND_CODES = (126, 127)
NEEDED = re.compile(r"\(NEEDED\)\s+Shared library: \[(.+?)\]")
SEARCH_PATH = re.compile(r"\((?:RUNPATH|RPATH)\)\s+Library r(?:un)?path: \[(.+?)\]")
LDCONFIG_FALLBACKS = ("/sbin/ldconfig", "/usr/sbin/ldconfig")

Capture = Callable[[list[str]], object]


def parse_ldconfig(text: str) -> set[str]:
    return {line.split()[0] for line in text.splitlines() if line.startswith(("\t", " ")) and line.strip()}


def host_library_names() -> set[str] | None:
    ldconfig = shutil.which("ldconfig") or next((p for p in LDCONFIG_FALLBACKS if Path(p).exists()), None)
    if ldconfig is None:
        return None
    done = subprocess.run([ldconfig, "-p"], capture_output=True, text=True)
    return parse_ldconfig(done.stdout) if done.returncode == 0 else None


def _host_folder(folder: str, origin: str, workdir: Path) -> Path | None:
    folder = posixpath.normpath(folder.replace("${ORIGIN}", origin).replace("$ORIGIN", origin))
    if folder == MOUNT:
        return workdir
    if folder.startswith(MOUNT + "/"):
        return workdir / folder[len(MOUNT) + 1:]
    return None


def _owner(name: str, capture: Capture) -> str | None:
    found = capture(["dpkg", "-S", f"*/{name}"])
    if found.returncode != 0:
        return None
    for line in found.stdout.splitlines():
        if ": " in line and not line.startswith("diversion"):
            return line.rsplit(": ", 1)[0].split(", ")[0].split(":")[0]
    return None


def check(
    programs: list[str], workdir: Path | str, capture: Capture, host_libraries: set[str]
) -> tuple[list[HostLibrary], list[str]]:
    workdir = Path(workdir)
    missing: dict[str, HostLibrary] = {}
    for program in programs:
        inside = posixpath.join(MOUNT, Path(program).relative_to(workdir).as_posix())
        dynamic = capture(["readelf", "-d", inside])
        if dynamic.returncode in NOT_FOUND_CODES:
            return [], ["readelf is not available in the build container, so the host library check was skipped"]
        if dynamic.returncode != 0:
            continue
        origin = posixpath.dirname(inside)
        folders = [
            host for paths in SEARCH_PATH.findall(dynamic.stdout) for folder in paths.split(":")
            if (host := _host_folder(folder, origin, workdir)) is not None
        ]
        for name in NEEDED.findall(dynamic.stdout):
            if name in host_libraries or name in missing or any((f / name).exists() for f in folders):
                continue
            missing[name] = HostLibrary(name=name, package=_owner(name, capture))
    return list(missing.values()), []
