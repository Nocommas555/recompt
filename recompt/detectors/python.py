import tomllib

from recompt.detectors.common import min_version, req, root, step
from recompt.models import DetectContext, Finding, WorkingCopy


def _venv_python(host_os: str) -> str:
    return ".venv\\Scripts\\python.exe" if host_os == "windows" else ".venv/bin/python"


def read_pyproject(base) -> dict:
    path = base / "pyproject.toml"
    return tomllib.loads(path.read_text()) if path.exists() else {}


def is_installable(base, pyproject: dict) -> bool:
    return "build-system" in pyproject or (base / "setup.py").exists()


def detect(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    base = root(copy)
    pyproject = read_pyproject(base)
    project = pyproject.get("project")
    installable = is_installable(base, pyproject)
    requirements_txt = (base / "requirements.txt").exists()
    if not (installable or project is not None or requirements_txt):
        return []

    origin = "pyproject.toml" if pyproject else "setup.py" if (base / "setup.py").exists() else "requirements.txt"
    version = min_version((project or {}).get("requires-python"))
    system_python = "python" if ctx.host_os == "windows" else "python3"
    venv = _venv_python(ctx.host_os)

    steps = [step("setup", [system_python, "-m", "venv", ".venv"], origin)]
    if requirements_txt:
        steps.append(step("setup", [venv, "-m", "pip", "install", "-r", "requirements.txt"], "requirements.txt"))
    if installable:
        steps.append(step("setup", [venv, "-m", "pip", "install", "."], origin))
    elif project and project.get("dependencies"):
        steps.append(step("setup", [venv, "-m", "pip", "install", *project["dependencies"]], "pyproject.toml:dependencies"))

    return [
        Finding(
            detector="python",
            ecosystem="python",
            requirements=[req("python", origin, version)],
            steps=steps,
        )
    ]
