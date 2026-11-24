import shlex

from recompt.models import InstallProposal, Requirement
from recompt.pkgmgr.toolchains import GO_ARCHIVE, RUSTUP, TOOLCHAINS, TOOLS_VENV, install_step


def propose(requirements: list[Requirement]) -> list[InstallProposal]:
    packages: list[str] = []
    special: dict[str, InstallProposal] = {}

    def add(*names: str) -> None:
        packages.extend(n for n in names if n not in packages)

    pypi: list[str] = []
    for req in requirements:
        info = TOOLCHAINS.get(req.tool)
        if info is None:
            add(req.tool)
        elif info.pypi and req.min_version:
            add("python3", "python3-venv")
            pypi.append(f"{info.pypi}>={req.min_version}")
        elif info.installer == "package":
            add(*info.apt)
        elif info.installer == "rustup":
            special["rustup"] = InstallProposal(
                manager="rustup", packages=["rustup"], commands=[install_step(RUSTUP, as_root=True, shell="sh")]
            )
        elif info.installer == "go-archive":
            special["go-archive"] = InstallProposal(
                manager="go-archive", packages=["go"], commands=[install_step(GO_ARCHIVE, as_root=True, shell="sh")]
            )
        elif info.installer == "npm":
            add(*TOOLCHAINS["node"].apt)
            npm = special.setdefault("npm", InstallProposal(manager="npm"))
            npm.packages.append(req.tool)
            npm.commands.append(install_step(["npm", "install", "-g", req.tool], as_root=True))

    proposals = []
    if packages:
        command = "apt-get install -y --no-install-recommends " + " ".join(packages)
        proposals.append(
            InstallProposal(manager="apt", packages=packages, commands=[install_step(command, as_root=True, shell="sh")])
        )
    if pypi:
        command = f"python3 -m venv {TOOLS_VENV} && {TOOLS_VENV}/bin/pip install {shlex.join(pypi)}"
        proposals.append(
            InstallProposal(manager="pip", packages=pypi, commands=[install_step(command, as_root=True, shell="sh")])
        )
    return proposals + list(special.values())
