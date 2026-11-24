import re
from pathlib import Path

import yaml

from recompt.detectors.ci_common import NOT_FOR_BUILDING, process_script
from recompt.detectors.common import min_version, root
from recompt.models import DetectContext, Finding, PlanNote, Requirement, Source, WorkingCopy

SETUP_ACTION = re.compile(r"^actions/setup-(\w+)@")
MATRIX_REF = re.compile(r"\$\{\{\s*matrix\.(\w+)\s*\}\}")
SHELLS = {"bash": "bash", "sh": "sh", "pwsh": "pwsh", "powershell": "pwsh", "cmd": "cmd"}


def _label_os(label: str) -> str | None:
    label = label.lower()
    if label.startswith(("ubuntu", "linux")):
        return "linux"
    if label.startswith("macos"):
        return "macos"
    if label.startswith("windows"):
        return "windows"
    return None


def _job_oses(job: dict) -> list[str]:
    runs_on = job.get("runs-on", "")
    labels = runs_on if isinstance(runs_on, list) else [str(runs_on)]
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    expanded: list[str] = []
    for label in labels:
        ref = MATRIX_REF.search(label)
        if ref and isinstance(matrix.get(ref.group(1)), list):
            expanded += [str(v) for v in matrix[ref.group(1)]]
        else:
            expanded.append(label)
    return [os for os in map(_label_os, expanded) if os]


def _workflows(base: Path) -> list[tuple[str, dict]]:
    folder = base / ".github" / "workflows"
    if not folder.is_dir():
        return []
    files = sorted([*folder.glob("*.yml"), *folder.glob("*.yaml")])
    result = []
    for f in files:
        data = yaml.safe_load(f.read_text()) or {}
        if isinstance(data, dict):
            result.append((f.name, data))
    return result


def _select_job(workflows, host_os: str):
    jobs = [
        (file, data, name, job)
        for file, data in workflows
        for name, job in (data.get("jobs") or {}).items()
        if isinstance(job, dict)
    ]
    for want in (host_os, "linux"):
        for entry in jobs:
            if want in _job_oses(entry[3]):
                return entry
    return jobs[0] if jobs else None


def _default_shell(data: dict, job: dict, host_os: str) -> str:
    for scope in (job, data):
        shell = ((scope.get("defaults") or {}).get("run") or {}).get("shell")
        if shell:
            return SHELLS.get(shell, "bash")
    return "pwsh" if host_os == "windows" else "bash"


def detect(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    selected = _select_job(_workflows(root(copy)), ctx.host_os)
    if not selected:
        return []
    file, data, name, job = selected
    origin = f".github/workflows/{file}:{name}"
    default_shell = _default_shell(data, job, ctx.host_os)

    finding = Finding(detector="github_actions")
    for item in job.get("steps") or []:
        uses = item.get("uses")
        if uses:
            setup = SETUP_ACTION.match(uses)
            if setup:
                lang = setup.group(1)
                version = (item.get("with") or {}).get(f"{lang}-version")
                finding.requirements.append(
                    Requirement(tool=lang, min_version=min_version(str(version or "")), source=Source.CI, origin=origin)
                )
            continue
        run = item.get("run")
        if not run:
            continue
        label = item.get("name") or run.splitlines()[0]
        if "${{" in run:
            finding.notes.append(PlanNote(kind="skipped", message=f"CI step uses expressions: {run.strip()}", sources=[origin]))
            continue
        if NOT_FOR_BUILDING.search(item.get("name", "")) or NOT_FOR_BUILDING.search(run):
            finding.notes.append(PlanNote(kind="skipped", message=f"CI step not needed to build: {label}", sources=[origin]))
            continue
        steps, requirements = process_script(
            run.splitlines(),
            origin=origin,
            shell=SHELLS.get(item.get("shell", ""), default_shell),
            cwd=item.get("working-directory", "."),
            host_os=ctx.host_os,
        )
        finding.steps += steps
        finding.requirements += requirements
    return [finding]
