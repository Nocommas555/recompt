import shlex
from pathlib import Path

from recompt.models import BuildPlan, InstallProposal, RunResult, Step
from recompt.source import strip_credentials


def command_text(command) -> str:
    return command if isinstance(command, str) else shlex.join(command)


def format_plan(plan: BuildPlan, proposals: list[InstallProposal]) -> str:
    lines = [f"Plan ({plan.project_kind} project):"]
    for step in plan.steps:
        mark = "  [needs your OK]" if step.needs_confirm else ""
        first, *rest = command_text(step.command).splitlines() or [""]
        lines.append(f"  {step.kind:7} {first}   (from {step.origin or step.source.value}){mark}")
        lines += [f"          {more}" for more in rest]
    for target in plan.targets:
        lines.append(f"  target  {target.name}" + (f" -> {target.expected_path}" if target.expected_path else ""))
    installs = [p for p in proposals if p.packages]
    if installs:
        lines.append("Dependencies:")
        lines += [f"  {p.manager}: {' '.join(p.packages)}" for p in installs]
    if plan.notes:
        lines.append("Notes:")
        lines += [f"  {n.kind}: {n.message}" for n in plan.notes]
    return "\n".join(lines)


def format_result(result: RunResult) -> str:
    lines = []
    if result.status == "ok":
        if result.program_path:
            lines.append(f"Built program: {result.program_path}")
        if result.launch_command:
            lines.append(f"Launch with: {result.launch_command}")
    else:
        if result.failed_step:
            lines.append(f"Failed step: {command_text(result.failed_step.command)}  (from {result.failed_step.origin})")
        if result.error_output:
            lines += ["Last output:", *[f"  {line}" for line in result.error_output.splitlines()]]
        if result.completed_steps:
            lines.append(f"Completed steps: {len(result.completed_steps)}")
    if result.missing:
        lines.append("Missing: " + ", ".join(r.tool for r in result.missing))
    if result.log_path:
        lines.append(f"Log: {result.log_path}")
    return "\n".join(lines)


class RunLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")

    def _write(self, text: str) -> None:
        self._file.write(strip_credentials(text) + "\n")
        self._file.flush()

    def command(self, step: Step) -> None:
        self._write(f"$ {command_text(step.command)}")

    def line(self, text: str) -> None:
        self._write(text)

    def close(self) -> None:
        self._file.close()
