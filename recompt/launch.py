import json
import tomllib
from pathlib import Path

from recompt.models import WorkingCopy


def _node(base: Path) -> list[str] | None:
    path = base / "package.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text() or "{}")
    if "start" in data.get("scripts", {}):
        manager = "pnpm" if (base / "pnpm-lock.yaml").exists() else "yarn" if (base / "yarn.lock").exists() else "npm"
        return [manager, "start"]
    bin_field = data.get("bin")
    if isinstance(bin_field, dict) and bin_field:
        return ["node", next(iter(bin_field.values()))]
    if isinstance(bin_field, str):
        return ["node", bin_field]
    if data.get("main"):
        return ["node", data["main"]]
    return None


def _python(base: Path, host_os: str) -> list[str] | None:
    windows = host_os == "windows"
    venv_bin = ".venv\\Scripts\\" if windows else ".venv/bin/"
    python = venv_bin + ("python.exe" if windows else "python")

    pyproject = base / "pyproject.toml"
    if pyproject.exists():
        scripts = tomllib.loads(pyproject.read_text()).get("project", {}).get("scripts", {})
        if scripts:
            name = next(iter(scripts))
            return [venv_bin + name + (".exe" if windows else "")]
    for folder in (base, base / "src"):
        if folder.is_dir():
            for main in sorted(folder.glob("*/__main__.py")):
                return [python, "-m", main.parent.name]
    for script in ("main.py", "app.py"):
        if (base / script).exists():
            return [python, script]
    return None


def resolve_launch(copy: WorkingCopy, ecosystem: str | None, host_os: str) -> list[str] | None:
    base = Path(copy.path)
    if ecosystem == "node":
        return _node(base)
    if ecosystem == "python":
        return _python(base, host_os)
    return None
