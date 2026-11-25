import os
import shlex
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

from recompt import collect as collect_mod
from recompt import deps, errors, hostlibs, planner, runners, source
from recompt.detectors import detect_all
from recompt.detectors import readme as readme_detector
from recompt.models import (
    BuildPlan,
    DetectContext,
    InstallProposal,
    Requirement,
    RunResult,
    Source,
    Step,
)

STATUS = {
    errors.BuildFailedError: "build_failed",
    errors.InvalidInputError: "invalid_input",
    errors.DepsMissingError: "deps_missing",
    errors.NoRunnableOutputError: "no_runnable_output",
    errors.NoPlanError: "no_plan",
    errors.StepTimeoutError: "timeout",
    errors.CancelledError: "cancelled",
}


@dataclass
class RunOptions:
    source: str
    ref: str | None = None
    preview: bool = False
    host_build: bool = False
    timeout: int = 1800
    yes: bool = False


class UI(Protocol):
    def warn(self, msg: str) -> None: ...
    def notice(self, msg: str) -> None: ...
    def show_plan(self, plan: BuildPlan, proposals: list[InstallProposal]) -> None: ...
    def confirm_installs(self, proposals: list[InstallProposal]) -> bool: ...
    def confirm_prose(self, steps: list[Step]) -> bool: ...
    def choose(self, prompt: str, options: list[str]) -> str: ...
    def step_started(self, step: Step) -> None: ...
    def output(self, line: str) -> None: ...


class NoticingBackend:
    def __init__(self, backend, ui: UI):
        self.backend, self.ui = backend, ui
        self.name, self.model = backend.name, backend.model

    def extract_plan(self, sections):
        self.ui.notice(f"Sending {len(sections)} README section(s) to the Claude API ({self.model})")
        return self.backend.extract_plan(sections)


def _as_text(command) -> str:
    return command if isinstance(command, str) else shlex.join(command)


class Pipeline:
    def __init__(
        self,
        ui: UI,
        *,
        host_os: str,
        llm=None,
        resolve=None,
        detect=detect_all,
        readme=readme_detector.detect,
        build_plan=planner.build_plan,
        propose=deps.propose,
        missing=deps.missing,
        make_runner=runners.make_runner,
        collect=collect_mod.collect,
        host_check=hostlibs.check,
        host_libraries=hostlibs.host_library_names,
        clock=time.time,
        run_id: str | None = None,
    ):
        self.ui = ui
        self.host_os = host_os
        self.llm = NoticingBackend(llm, ui) if llm is not None and llm.name == "claude" else llm
        self.resolve = resolve or (lambda value, ref: source.resolve(value, ref))
        self.detect = detect
        self.readme = readme
        self.build_plan = build_plan
        self.propose = propose
        self.missing = missing
        self.make_runner = make_runner
        self.collect = collect
        self.host_check = host_check
        self.host_libraries = host_libraries
        self.clock = clock
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.result = RunResult(status="ok")

    def run(self, opts: RunOptions) -> RunResult:
        try:
            return self._run(opts)
        except errors.RecomptError as exc:
            self.result.status = STATUS.get(type(exc), "build_failed")
            exc.result = self.result
            raise

    def _choose(self, prompt: str, options: list[str]) -> str:
        self.result.prompts_asked += 1
        return self.ui.choose(prompt, options)

    def _dependencies(self, plan: BuildPlan, opts: RunOptions) -> list[Step]:
        if self.host_os == "linux" and opts.host_build:
            absent = self.missing(plan.requirements, self.host_os)
            if absent:
                self.result.missing = absent
                self.ui.warn("Not installed on this machine (recompt does not install on the host with --host-build): "
                             + ", ".join(r.tool for r in absent))
            return []

        proposals = self._proposals
        report = [pkg for p in proposals if p.manager == "report-only" for pkg in p.packages]
        if report:
            self.result.missing = [Requirement(tool=t, source=Source.BUILD_FILE) for t in report]
            self.ui.warn("Cannot be installed automatically, install them yourself if the build needs them: "
                         + ", ".join(report))
        installable = [p for p in proposals if p.manager != "report-only"]
        if not installable:
            return []
        needs_consent = self.host_os != "linux" and not opts.yes
        if needs_consent and not self.ui.confirm_installs(installable):
            self.result.missing += [Requirement(tool=pkg, source=Source.BUILD_FILE) for p in installable for pkg in p.packages]
            raise errors.DepsMissingError("Missing dependencies were not installed: "
                                          + ", ".join(pkg for p in installable for pkg in p.packages))
        return deps.install_steps(installable, approved=True)

    def _check_host_libraries(self, runner, program: str, workdir: str) -> None:
        libraries = self.host_libraries()
        if libraries is None:
            self.ui.warn("ldconfig is not available on this machine, so the host library check was skipped")
            return
        missing, warnings = self.host_check([program], workdir, runner.capture, libraries)
        for warning in warnings:
            self.ui.warn(warning)
        if not missing:
            return
        self.result.missing_host_libraries = missing
        packages = [lib.package for lib in missing if lib.package]
        unowned = [lib.name for lib in missing if not lib.package]
        message = ("The program needs shared libraries that are not installed on this machine: "
                   + ", ".join(lib.name for lib in missing))
        if packages:
            message += "\n  Install them with: sudo apt install " + " ".join(dict.fromkeys(packages))
        if unowned:
            message += "\n  No apt package in the build container provides: " + ", ".join(unowned)
        self.ui.warn(message)

    def _run(self, opts: RunOptions) -> RunResult:
        copy = self.resolve(opts.source, opts.ref)
        if copy.in_place:
            self.ui.warn(f"Building in place: build output is written into {copy.path}")
        ctx = DetectContext(host_os=self.host_os, llm=self.llm)
        findings = self.detect(copy, ctx)
        plan = self.build_plan(
            findings, copy=copy, host_os=self.host_os, readme_fallback=lambda: self.readme(copy, ctx)
        )
        if len(plan.targets) > 1:
            chosen = self._choose("Several programs can be built. Which one?", [t.name for t in plan.targets])
            plan.targets = [t for t in plan.targets if t.name == chosen]

        skip_proposals = self.host_os == "linux" and opts.host_build
        self._proposals = [] if skip_proposals else self.propose(plan.requirements, self.host_os)
        self.ui.show_plan(plan, self._proposals)
        if opts.preview:
            return self.result

        prose = [s for s in plan.steps if s.needs_confirm and s.kind != "launch"]
        if prose and not self.ui.confirm_prose(prose):
            raise errors.NoPlanError("Steps taken from README text were not approved")

        install = self._dependencies(plan, opts)
        work = [s for s in plan.steps if s.kind in ("setup", "build")]

        runner = self.make_runner(
            host_os=self.host_os, host_build=opts.host_build, workdir=copy.path, timeout=opts.timeout,
            on_output=self.ui.output, run_id=self.run_id, env=dict(os.environ),
        )
        started = self.clock()
        try:
            runner.start()
            for warning in getattr(runner, "warnings", []):
                self.ui.warn(warning)
            for step in install + work:
                self.ui.step_started(step)
                result = runner.run(step)
                if result.exit_code != 0:
                    self.result.failed_step = step
                    self.result.error_output = result.output_tail
                    raise errors.BuildFailedError(f"Step failed with exit code {result.exit_code}: {_as_text(step.command)}")
                self.result.completed_steps.append(step)

            collected = self.collect(plan, copy.path, started, self.host_os)
            if collected.launch is not None:
                if hasattr(runner, "commit"):
                    tag = runner.commit(copy.url, copy.ref)
                    self.result.launch_command = _as_text(runner.launch_command(tag, collected.launch))
                else:
                    self.result.launch_command = f"cd {shlex.quote(copy.path)} && {_as_text(collected.launch)}"
            else:
                programs = collected.programs
                self.result.program_path = (
                    programs[0] if len(programs) == 1 else self._choose("Several programs were built. Which one?", programs)
                )
                if self.host_os == "linux" and not opts.host_build and hasattr(runner, "capture"):
                    self._check_host_libraries(runner, self.result.program_path, copy.path)
            return self.result
        except (errors.StepTimeoutError, errors.CancelledError, KeyboardInterrupt):
            runner.kill()
            raise
        finally:
            runner.stop()
