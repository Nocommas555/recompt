import json

from recompt.detectors.common import min_version, req, root, step
from recompt.models import DetectContext, Finding, WorkingCopy

ORIGIN = "package.json"


def _manager(base) -> tuple[str, list[str]]:
    if (base / "pnpm-lock.yaml").exists():
        return "pnpm", ["pnpm", "install"]
    if (base / "yarn.lock").exists():
        return "yarn", ["yarn", "install"]
    if (base / "package-lock.json").exists():
        return "npm", ["npm", "ci"]
    return "npm", ["npm", "install"]


def detect(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    base = root(copy)
    path = base / ORIGIN
    if not path.exists():
        return []
    data = json.loads(path.read_text() or "{}")
    manager, install = _manager(base)

    requirements = [req("node", f"{ORIGIN}:engines.node", min_version(data.get("engines", {}).get("node")))]
    if manager != "npm":
        requirements.append(req(manager, ORIGIN))

    steps = [step("setup", install, ORIGIN)]
    if "build" in data.get("scripts", {}):
        steps.append(step("build", [manager, "run", "build"], f"{ORIGIN}:scripts.build"))

    return [Finding(detector="node", ecosystem="node", requirements=requirements, steps=steps)]
