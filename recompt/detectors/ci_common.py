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


CMAKE_DEFINE = re.compile(r"(?<![\w-])-D([A-Za-z_]\w*)=([^\s\"')]*)")
MACHINE_SPECIFIC_OPTIONS = {"CMAKE_BUILD_TYPE", "CMAKE_PREFIX_PATH"}


def cmake_options(script: str) -> list[str]:
    if "cmake" not in script.lower():
        return []
    options = []
    for name, value in CMAKE_DEFINE.findall(script):
        if not value or "$" in value or "{" in value or name in MACHINE_SPECIFIC_OPTIONS:
            continue
        option = f"-D{name}={value}"
        if option not in options:
            options.append(option)
    return options


CMAKE_GENERATOR = re.compile(r'(?<!\S)-G\s*(?:"([^"]+)"|(\S+))')
CMAKE_BUILD_DIR = re.compile(r'(?<!\S)-B\s*(?:"([^"]+)"|(\S+))')


def _fixed(match) -> str | None:
    if not match:
        return None
    value = match.group(1) or match.group(2)
    return None if "$" in value or "{" in value else value


def cmake_configure(script: str) -> tuple[str | None, str | None]:
    for line in join_continuations(script.splitlines()):
        if re.search(r"\bcmake\b", line) and re.search(r"(?<!\S)-S(?:\s|$)", line):
            return _fixed(CMAKE_GENERATOR.search(line)), _fixed(CMAKE_BUILD_DIR.search(line))
    return None, None


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
