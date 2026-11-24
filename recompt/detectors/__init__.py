from typing import Callable

from recompt.detectors import cfamily, dockerfile, github_actions, gitlab_ci, go, node, python, rust
from recompt.models import DetectContext, Finding, WorkingCopy

Detector = Callable[[WorkingCopy, DetectContext], list[Finding]]

REGISTRY: list[Detector] = [
    node.detect,
    python.detect,
    rust.detect,
    go.detect,
    cfamily.detect,
    github_actions.detect,
    gitlab_ci.detect,
    dockerfile.detect,
]


def detect_all(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    return [finding for detector in REGISTRY for finding in detector(copy, ctx)]
