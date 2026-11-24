import re

from recompt.detectors.common import exe, req, root, step
from recompt.models import DetectContext, Finding, Target, WorkingCopy

ORIGIN = "go.mod"
MODULE = re.compile(r"^module\s+(\S+)", re.M)
GO_DIRECTIVE = re.compile(r"^go\s+(\d+(?:\.\d+)*)", re.M)
PACKAGE_MAIN = re.compile(r"^package\s+main\b", re.M)


def _is_main(folder) -> bool:
    return any(PACKAGE_MAIN.search(f.read_text(errors="ignore")) for f in folder.glob("*.go"))


def detect(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    base = root(copy)
    path = base / ORIGIN
    if not path.exists():
        return []
    text = path.read_text()
    module = MODULE.search(text)
    version = GO_DIRECTIVE.search(text)

    mains: list[tuple[str, str]] = []
    if _is_main(base):
        mains.append((module.group(1).rsplit("/", 1)[-1] if module else base.name, "."))
    cmd = base / "cmd"
    if cmd.is_dir():
        mains += [(d.name, f"./cmd/{d.name}") for d in sorted(cmd.iterdir()) if d.is_dir() and _is_main(d)]

    if mains:
        steps = [step("build", ["go", "build", "-o", f"bin/{exe(n, ctx.host_os)}", p], ORIGIN) for n, p in mains]
        targets = [Target(name=n, expected_path=f"bin/{exe(n, ctx.host_os)}") for n, _ in mains]
    else:
        steps, targets = [step("build", ["go", "build", "./..."], ORIGIN)], []

    return [
        Finding(
            detector="go",
            ecosystem="go",
            requirements=[req("go", f"{ORIGIN}:go", version.group(1) if version else None)],
            steps=steps,
            targets=targets,
        )
    ]
