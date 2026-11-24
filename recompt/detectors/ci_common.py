import re

from recompt.models import Requirement, Source, Step

INSTALL = re.compile(
    r"^(?:sudo\s+)?(?:(?P<apt>apt-get|apt)\s+install|brew\s+install|choco\s+install|winget\s+install"
    r"|apk\s+add|(?:dnf|yum)\s+install)\b(?P<rest>.*)$"
)
APT_UPDATE = re.compile(r"^(?:sudo\s+)?(?:apt-get|apt)\s+update\b")
NOT_FOR_BUILDING = re.compile(
    r"\b(test|tests|check|lint|clippy|fmt|format|coverage|codecov|upload|deploy|publish)\b", re.I
)
SHELL_STOP = {"&&", "||", ";", "|"}


def parse_install(line: str) -> tuple[bool, list[str]] | None:
    match = INSTALL.match(line.strip())
    if not match:
        return None
    packages = []
    for token in match.group("rest").split():
        if token in SHELL_STOP:
            break
        if token.startswith("-") or "$" in token or token == "\\":
            continue
        packages.append(token)
    return bool(match.group("apt")), packages


def _apt_step_command(line: str) -> str:
    command = re.sub(r"^sudo\s+", "", line.strip())
    if not re.search(r"(^|\s)(-y|--yes|--assume-yes)(\s|$)", command):
        command = re.sub(r"\binstall\b", "install -y", command, count=1)
    return command


def join_continuations(lines: list[str]) -> list[str]:
    joined: list[str] = []
    pending = ""
    for raw in lines:
        line = raw.rstrip()
        if line.endswith("\\"):
            pending += line[:-1].strip() + " "
            continue
        joined.append(pending + line.strip() if pending else line)
        pending = ""
    if pending:
        joined.append(pending.strip())
    return joined


def process_script(
    lines: list[str],
    *,
    origin: str,
    shell: str,
    cwd: str,
    host_os: str,
    source: Source = Source.CI,
) -> tuple[list[Step], list[Requirement]]:
    installs: list[Step] = []
    requirements: list[Requirement] = []
    kept: list[str] = []
    for raw in join_continuations(lines):
        line = raw.strip()
        if not line or line.startswith("#") or APT_UPDATE.match(line):
            continue
        parsed = parse_install(line)
        if parsed is None:
            kept.append(line)
            continue
        is_apt, packages = parsed
        requirements += [Requirement(tool=p, source=source, origin=origin) for p in packages]
        if is_apt and host_os == "linux":
            installs.append(
                Step(
                    kind="install",
                    command=_apt_step_command(line),
                    shell="sh",
                    cwd="/",
                    as_root=True,
                    source=source,
                    origin=origin,
                )
            )
    steps = installs
    if kept:
        steps = steps + [
            Step(kind="build", command="\n".join(kept), shell=shell, cwd=cwd, source=source, origin=origin)
        ]
    return steps, requirements
