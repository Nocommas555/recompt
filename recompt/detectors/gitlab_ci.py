import re

import yaml

from recompt.detectors.ci_common import cmake_configure, cmake_options, process_script
from recompt.detectors.common import root
from recompt.models import DetectContext, Finding, WorkingCopy

ORIGIN = ".gitlab-ci.yml"
RESERVED = {
    "stages", "variables", "default", "include", "workflow", "image",
    "services", "before_script", "after_script", "cache",
}
BUILD_NAME = re.compile(r"build|compile", re.I)


def _as_list(value) -> list[str]:
    if value is None:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def detect(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    path = root(copy) / ORIGIN
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    jobs = [
        (name, job)
        for name, job in data.items()
        if isinstance(job, dict) and "script" in job and not name.startswith(".") and name not in RESERVED
    ]
    if not jobs:
        return []
    name, job = next(((n, j) for n, j in jobs if BUILD_NAME.search(n)), jobs[0])

    before = job["before_script"] if "before_script" in job else data.get("before_script")
    lines = _as_list(before) + _as_list(job["script"])
    steps, requirements = process_script(
        lines,
        origin=f"{ORIGIN}:{name}",
        shell="sh",
        cwd=".",
        host_os=ctx.host_os,
    )
    script = "\n".join(lines)
    generator, build_dir = cmake_configure(script)
    return [
        Finding(
            detector="gitlab_ci",
            requirements=requirements,
            steps=steps,
            cmake_options=cmake_options(script),
            cmake_generator=generator,
            cmake_build_dir=build_dir,
        )
    ]
