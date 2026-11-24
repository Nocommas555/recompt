from typing import Callable

from recompt.errors import NoPlanError
from recompt.launch import resolve_launch
from recompt.models import BuildPlan, Finding, PlanNote, Requirement, Source, Step, WorkingCopy

PRIORITY = [Source.BUILD_FILE, Source.CI, Source.DOCKERFILE, Source.PROSE]
DETECTOR_SOURCE = {
    "github_actions": Source.CI,
    "gitlab_ci": Source.CI,
    "dockerfile": Source.DOCKERFILE,
    "readme": Source.PROSE,
}
INTERPRETED = {"node", "python"}
COMPILED = {"rust", "go", "cfamily"}

ReadmeFallback = Callable[[], list[Finding]]


def _source(finding: Finding) -> Source:
    return DETECTOR_SOURCE.get(finding.detector, Source.BUILD_FILE)


def _work(findings: list[Finding]) -> list[Step]:
    return [s for f in findings for s in f.steps if s.kind != "install"]


def _origins(steps: list[Step]) -> list[str]:
    return sorted({s.origin for s in steps})


def _requirements(groups: dict[Source, list[Finding]]) -> list[Requirement]:
    merged: dict[str, Requirement] = {}
    for source in PRIORITY:
        for req in (r for f in groups[source] for r in f.requirements):
            kept = merged.get(req.tool)
            if kept is None:
                merged[req.tool] = req
            elif kept.min_version is None and req.min_version:
                merged[req.tool] = kept.model_copy(update={"min_version": req.min_version})
    return list(merged.values())


def _project_kind(primary: list[Finding], steps: list[Step]) -> str:
    ecosystem = next((f.ecosystem for f in primary if f.ecosystem), None)
    if ecosystem in INTERPRETED:
        return "interpreted"
    if ecosystem in COMPILED:
        return "compiled"
    kinds = {s.kind for s in steps}
    if "launch" in kinds:
        return "interpreted"
    return "compiled" if "build" in kinds else "interpreted"


def build_plan(
    findings: list[Finding],
    *,
    copy: WorkingCopy,
    host_os: str,
    readme_fallback: ReadmeFallback | None,
) -> BuildPlan:
    findings = list(findings)
    if not _work(findings) and readme_fallback is not None:
        findings += readme_fallback()

    groups: dict[Source, list[Finding]] = {s: [] for s in PRIORITY}
    for f in findings:
        groups[_source(f)].append(f)
    notes = [n for f in findings for n in f.notes]

    ranked = [s for s in PRIORITY if _work(groups[s])]
    if not ranked:
        detail = "; ".join(n.message for n in notes)
        raise NoPlanError("No build instructions found" + (f" ({detail})" if detail else ""))

    primary_source, others = ranked[0], ranked[1:]
    primary = groups[primary_source]
    steps = _work(primary)

    primary_ecosystem = next((f.ecosystem for f in primary if f.ecosystem), None)
    if primary_ecosystem not in INTERPRETED and not any(s.kind == "build" for s in steps):
        donor = next((src for src in others if any(s.kind == "build" for s in _work(groups[src]))), None)
        if donor is not None:
            filled = [s for s in _work(groups[donor]) if s.kind == "build"]
            steps += filled
            notes.append(
                PlanNote(
                    kind="warning",
                    message=f"No build step in {', '.join(_origins(_work(primary)))}; using build steps from {donor.value}",
                    sources=_origins(filled),
                )
            )
            others = [src for src in others if src != donor]

    for src in others:
        ignored = _work(groups[src])
        notes.append(
            PlanNote(
                kind="conflict",
                message=f"Using steps from {primary_source.value}; ignored {len(ignored)} step(s) from {src.value}",
                sources=_origins(_work(primary)) + _origins(ignored),
            )
        )

    kind = _project_kind(primary, steps)
    if kind == "interpreted" and not any(s.kind == "launch" for s in steps):
        ecosystem = next((f.ecosystem for f in primary if f.ecosystem), None)
        command = resolve_launch(copy, ecosystem, host_os)
        if command:
            steps.append(Step(kind="launch", command=command, source=primary_source, origin="launch resolver"))

    return BuildPlan(
        project_kind=kind,
        steps=steps,
        requirements=_requirements(groups),
        targets=[t for f in primary for t in f.targets],
        notes=notes,
    )
