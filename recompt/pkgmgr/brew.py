from recompt.models import InstallProposal, Requirement
from recompt.pkgmgr.toolchains import RUSTUP, TOOLCHAINS, install_step


def propose(requirements: list[Requirement]) -> list[InstallProposal]:
    packages: list[str] = []
    report: list[str] = []
    extra: list[InstallProposal] = []

    for req in requirements:
        info = TOOLCHAINS.get(req.tool)
        if info and info.installer == "rustup":
            if not any(p.manager == "rustup" for p in extra):
                extra.append(
                    InstallProposal(manager="rustup", packages=["rustup"], commands=[install_step(RUSTUP, as_root=False, shell="sh")])
                )
        elif info and info.installer == "npm":
            extra.append(
                InstallProposal(manager="npm", packages=[req.tool], commands=[install_step(["npm", "install", "-g", req.tool], as_root=False)])
            )
        elif info and info.brew:
            if info.brew not in packages:
                packages.append(info.brew)
        else:
            report.append(req.tool)

    proposals = []
    if packages:
        proposals.append(
            InstallProposal(manager="brew", packages=packages, commands=[install_step(["brew", "install", *packages], as_root=False)])
        )
    if report:
        proposals.append(InstallProposal(manager="report-only", packages=report))
    return proposals + extra
