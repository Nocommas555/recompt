import tomllib

from recompt.detectors.common import min_version, req, root, step
from recompt.models import DetectContext, Finding, WorkingCopy


def _venv_python(host_os: str) -> str:
    return ".venv\\Scripts\\python.exe" if host_os == "windows" else ".venv/bin/python"


def detect(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    base = root(copy)
    pyproject = base / "pyproject.toml"
    setup_py = base / "setup.py"
    requirements_txt = base / "requirements.txt"
    if not (pyproject.exists() or setup_py.exists() or requirements_txt.exists()):
        return []

    version = None
    origin = "setup.py" if setup_py.exists() else "requirements.txt"
    if pyproject.exists():
        origin = "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        version = min_version(data.get("project", {}).get("requires-python"))

    system_python = "python" if ctx.host_os == "windows" else "python3"
    venv = _venv_python(ctx.host_os)
    steps = [step("setup", [system_python, "-m", "venv", ".venv"], origin)]
    if requirements_txt.exists():
        steps.append(step("setup", [venv, "-m", "pip", "install", "-r", "requirements.txt"], "requirements.txt"))
    if pyproject.exists() or setup_py.exists():
        steps.append(step("setup", [venv, "-m", "pip", "install", "."], origin))

    return [
        Finding(
            detector="python",
            ecosystem="python",
            requirements=[req("python", origin, version)],
            steps=steps,
        )
    ]
