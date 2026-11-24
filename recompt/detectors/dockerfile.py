import re

from recompt.detectors.ci_common import parse_install
from recompt.detectors.common import root
from recompt.models import DetectContext, Finding, PlanNote, Requirement, Source, WorkingCopy

ORIGIN = "Dockerfile"


def _instructions(text: str) -> list[str]:
    joined = re.sub(r"\\\s*\n", " ", text)
    return [line.strip() for line in joined.splitlines() if line.strip() and not line.strip().startswith("#")]


def detect(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    path = root(copy) / ORIGIN
    if not path.exists():
        return []
    finding = Finding(detector="dockerfile")
    for line in _instructions(path.read_text()):
        keyword, _, body = line.partition(" ")
        keyword = keyword.upper()
        if keyword == "RUN":
            for piece in re.split(r"&&|;", body):
                parsed = parse_install(piece)
                if parsed:
                    finding.requirements += [
                        Requirement(tool=p, source=Source.DOCKERFILE, origin=ORIGIN) for p in parsed[1]
                    ]
        elif keyword == "EXPOSE":
            finding.notes.append(
                PlanNote(
                    kind="warning",
                    message=f"Dockerfile exposes port(s) {body.strip()}; recompt does not map ports",
                    sources=[ORIGIN],
                )
            )
    return [finding]
