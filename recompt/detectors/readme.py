import re
from pathlib import Path

from recompt.detectors.common import root
from recompt.llm.base import DocSection, LLMUnavailable
from recompt.models import DetectContext, Finding, PlanNote, Requirement, Source, Step, WorkingCopy

ROOT_PREFIXES = ("readme", "install", "building")
WANTED = re.compile(r"build|install|compil|usage|getting started|quick ?start", re.I)
ATX = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
SETEXT = re.compile(r"^(=+|-+)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def _doc_files(base: Path) -> list[Path]:
    files = [p for p in sorted(base.iterdir()) if p.is_file() and p.name.lower().startswith(ROOT_PREFIXES)]
    docs = base / "docs"
    if docs.is_dir():
        files += [p for p in sorted(docs.glob("*.md")) if p.name.lower().startswith("build")]
    return files


def _split(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    in_fence = False
    for i, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        atx = ATX.match(line)
        if atx:
            headings.append((i, i + 1, atx.group(1)))
        elif i > 0 and SETEXT.match(line) and len(line.strip()) >= 3 and lines[i - 1].strip():
            if headings and headings[-1][0] == i - 1:
                continue
            headings.append((i - 1, i + 1, lines[i - 1].strip()))
    sections = []
    for n, (_, body_start, title) in enumerate(headings):
        end = headings[n + 1][0] if n + 1 < len(headings) else len(lines)
        sections.append((title, "\n".join(lines[body_start:end]).strip()))
    return sections


def select_sections(copy: WorkingCopy) -> list[DocSection]:
    base = root(copy)
    result = []
    for path in _doc_files(base):
        rel = path.relative_to(base).as_posix()
        for title, body in _split(path.read_text(errors="ignore")):
            if WANTED.search(title):
                result.append(DocSection(file=rel, heading=title, text=body))
    return result


def detect(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    sections = select_sections(copy)
    if not sections:
        return []
    finding = Finding(detector="readme")
    if ctx.llm is None:
        finding.notes.append(PlanNote(kind="unavailable", message="README instructions found, but no LLM backend is available"))
        return [finding]
    try:
        plan = ctx.llm.extract_plan(sections)
    except LLMUnavailable as exc:
        finding.notes.append(PlanNote(kind="unavailable", message=f"README fallback unavailable: {exc}"))
        return [finding]

    origin = sections[0].file
    finding.requirements = [
        Requirement(tool=r.tool, min_version=r.min_version, source=Source.PROSE, origin=origin)
        for r in plan.requirements
    ]
    finding.steps = [
        Step(
            kind=s.kind,
            command=s.command,
            shell=s.shell,
            cwd=s.cwd,
            source=Source.PROSE,
            origin=origin,
            needs_confirm=True,
        )
        for s in plan.steps
    ]
    return [finding]
