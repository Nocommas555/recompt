import tomllib

from recompt.detectors.common import exe, req, root, step
from recompt.models import DetectContext, Finding, Target, WorkingCopy

ORIGIN = "Cargo.toml"


def detect(copy: WorkingCopy, ctx: DetectContext) -> list[Finding]:
    base = root(copy)
    path = base / ORIGIN
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text())
    package = data.get("package", {})
    rust_version = package.get("rust-version")
    if isinstance(rust_version, dict):
        rust_version = data.get("workspace", {}).get("package", {}).get("rust-version")

    names = [b["name"] for b in data.get("bin", []) if "name" in b]
    if not names and package.get("name") and (base / "src" / "main.rs").exists():
        names = [package["name"]]
    targets = [Target(name=n, expected_path=f"target/release/{exe(n, ctx.host_os)}") for n in names]

    return [
        Finding(
            detector="rust",
            ecosystem="rust",
            requirements=[req("cargo", f"{ORIGIN}:rust-version", rust_version)],
            steps=[step("build", ["cargo", "build", "--release"], ORIGIN)],
            targets=targets,
        )
    ]
