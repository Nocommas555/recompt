from recompt.models import InstallProposal, Requirement
from recompt.pkgmgr.toolchains import TOOLCHAINS, install_step

MSVC = "Microsoft.VisualStudio.2022.BuildTools"
MSVC_OVERRIDE = ["--override", "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"]


def _command(package_id: str) -> list[str]:
    command = ["winget", "install", "--id", package_id, "--exact"]
    return command + MSVC_OVERRIDE if package_id == MSVC else command


def propose(requirements: list[Requirement]) -> list[InstallProposal]:
    ids: list[str] = []
    report: list[str] = []
    extra: list[InstallProposal] = []

    for req in requirements:
        info = TOOLCHAINS.get(req.tool)
        if info and info.installer == "npm":
            extra.append(
                InstallProposal(manager="npm", packages=[req.tool], commands=[install_step(["npm", "install", "-g", req.tool], as_root=False)])
            )
        elif info and info.winget:
            if info.winget not in ids:
                ids.append(info.winget)
        else:
            report.append(req.tool)

    proposals = []
    if ids:
        proposals.append(
            InstallProposal(manager="winget", packages=ids, commands=[install_step(_command(i), as_root=False) for i in ids])
        )
    if report:
        proposals.append(InstallProposal(manager="report-only", packages=report))
    return proposals + extra
