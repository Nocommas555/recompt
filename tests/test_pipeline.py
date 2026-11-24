import pytest

from recompt.collect import Collected
from recompt.errors import BuildFailedError, CancelledError, DepsMissingError, NoPlanError, StepTimeoutError
from recompt.models import (
    BuildPlan,
    InstallProposal,
    Requirement,
    Source,
    Step,
    StepResult,
    Target,
    WorkingCopy,
)
from recompt.pipeline import Pipeline, RunOptions


def st(kind, cmd, **kw):
    return Step(kind=kind, command=cmd, source=kw.pop("source", Source.BUILD_FILE), **kw)


class FakeUI:
    def __init__(self, installs=True, prose=True, choice=None):
        self.events, self.installs, self.prose, self.choice = [], installs, prose, choice
        self.warnings, self.notices = [], []

    def warn(self, msg):
        self.warnings.append(msg)

    def notice(self, msg):
        self.notices.append(msg)

    def show_plan(self, plan, proposals):
        self.events.append("show_plan")

    def confirm_installs(self, proposals):
        self.events.append("confirm_installs")
        return self.installs

    def confirm_prose(self, steps):
        self.events.append("confirm_prose")
        return self.prose

    def choose(self, prompt, options):
        self.events.append("choose")
        return self.choice or options[0]

    def step_started(self, step):
        pass

    def output(self, line):
        pass


class FakeRunner:
    def __init__(self, events, fail_on=None, raise_on=None):
        self.events, self.fail_on, self.raise_on, self.ran, self.warnings = events, fail_on, raise_on, [], []

    def start(self):
        self.events.append("start")

    def run(self, step):
        if self.raise_on and step.command == self.raise_on[0]:
            raise self.raise_on[1]
        self.ran.append(step)
        self.events.append(f"run:{step.kind}")
        code = 2 if step.command == self.fail_on else 0
        return StepResult(step=step, exit_code=code, output_tail="error: boom" if code else "")

    def kill(self):
        self.events.append("kill")

    def stop(self):
        self.events.append("stop")

    def commit(self, url, ref):
        self.events.append("commit")
        return "recompt/abc"

    def launch_command(self, tag, argv):
        return ["podman", "run", tag, *argv]


COMPILED = BuildPlan(
    project_kind="compiled",
    steps=[
        st("install", "apt-get install -y libssl-dev", as_root=True, source=Source.CI),
        st("build", ["cargo", "build", "--release"]),
    ],
    requirements=[Requirement(tool="cargo", source=Source.BUILD_FILE)],
    targets=[Target(name="tool", expected_path="target/release/tool")],
)
INSTALL = InstallProposal(manager="apt", packages=["x"], commands=[st("install", "apt-get install -y x", as_root=True)])


def make(ui, plan=COMPILED, host_os="linux", proposals=(INSTALL,), runner_kw=None, copy=None, collected=None, llm=None):
    events = ui.events
    runner = FakeRunner(events, **(runner_kw or {}))
    made = []

    def make_runner(**kw):
        events.append("make_runner")
        made.append(kw)
        return runner

    p = Pipeline(
        ui,
        host_os=host_os,
        llm=llm,
        resolve=lambda source, ref: events.append("resolve") or (copy or WorkingCopy(path="/w", in_place=False, url="u")),
        detect=lambda copy, ctx: events.append("detect") or [],
        build_plan=lambda findings, **kw: events.append("plan") or plan.model_copy(deep=True),
        propose=lambda reqs, host: events.append("propose") or list(proposals),
        missing=lambda reqs, host: [r for r in reqs],
        make_runner=make_runner,
        collect=lambda plan, workdir, started, host: events.append("collect") or (collected or Collected(programs=["/w/target/release/tool"])),
        run_id="r1",
    )
    return p, runner, made


def opts(**kw):
    return RunOptions(source="https://example.org/r", **kw)


def test_stage_order_on_linux_and_installs_not_prompted():
    ui = FakeUI()
    p, runner, _ = make(ui)
    result = p.run(opts())
    assert ui.events == [
        "resolve", "detect", "plan", "propose", "show_plan",
        "make_runner", "start", "run:install", "run:build", "collect", "stop",
    ]
    assert [s.command for s in runner.ran] == ["apt-get install -y x", ["cargo", "build", "--release"]]
    assert result.status == "ok" and result.program_path == "/w/target/release/tool"
    assert len(result.completed_steps) == 2


def test_preview_stops_after_plan_without_runner():
    ui = FakeUI()
    p, _, made = make(ui)
    result = p.run(opts(preview=True))
    assert ui.events == ["resolve", "detect", "plan", "propose", "show_plan"]
    assert made == [] and result.status == "ok"


def test_host_installs_need_confirmation_before_runner_starts():
    ui = FakeUI()
    p, _, _ = make(ui, host_os="macos")
    p.run(opts())
    assert ui.events.index("confirm_installs") < ui.events.index("make_runner") < ui.events.index("start")


def test_yes_skips_install_confirmation():
    ui = FakeUI()
    p, runner, _ = make(ui, host_os="windows")
    p.run(opts(yes=True))
    assert "confirm_installs" not in ui.events
    assert runner.ran[0].command == "apt-get install -y x"


def test_declined_installs_stop_before_anything_runs():
    ui = FakeUI(installs=False)
    p, runner, made = make(ui, host_os="macos")
    with pytest.raises(DepsMissingError) as exc:
        p.run(opts())
    assert made == [] and runner.ran == []
    assert exc.value.result.status == "deps_missing"
    assert [r.tool for r in exc.value.result.missing] == ["x"]


def test_report_only_is_warned_and_run_continues():
    ui = FakeUI()
    report = InstallProposal(manager="report-only", packages=["libfoo"])
    p, _, _ = make(ui, host_os="macos", proposals=(report,))
    result = p.run(opts())
    assert result.status == "ok"
    assert any("libfoo" in w for w in ui.warnings)
    assert [r.tool for r in result.missing] == ["libfoo"]
    assert "confirm_installs" not in ui.events


def test_build_failure_records_failed_step_and_stops_runner():
    ui = FakeUI()
    p, _, _ = make(ui, runner_kw={"fail_on": ["cargo", "build", "--release"]})
    with pytest.raises(BuildFailedError) as exc:
        p.run(opts())
    r = exc.value.result
    assert r.status == "build_failed"
    assert r.failed_step.command == ["cargo", "build", "--release"]
    assert "boom" in r.error_output
    assert [s.kind for s in r.completed_steps] == ["install"]
    assert ui.events[-1] == "stop"


@pytest.mark.parametrize("error, status", [(StepTimeoutError("slow"), "timeout"), (CancelledError("stop"), "cancelled")])
def test_timeout_and_cancel_kill_then_stop(error, status):
    ui = FakeUI()
    p, _, _ = make(ui, runner_kw={"raise_on": (["cargo", "build", "--release"], error)})
    with pytest.raises(type(error)) as exc:
        p.run(opts())
    assert ui.events[-2:] == ["kill", "stop"]
    assert exc.value.result.status == status
    assert [s.kind for s in exc.value.result.completed_steps] == ["install"]


def test_several_targets_ask_and_count_prompt():
    ui = FakeUI(choice="b")
    plan = COMPILED.model_copy(update={"targets": [Target(name="a"), Target(name="b")]})
    p, _, _ = make(ui, plan=plan)
    result = p.run(opts())
    assert "choose" in ui.events and result.prompts_asked == 1


def test_several_found_programs_ask_which():
    ui = FakeUI(choice="/w/bin/b")
    p, _, _ = make(ui, collected=Collected(programs=["/w/bin/a", "/w/bin/b"]))
    result = p.run(opts())
    assert result.program_path == "/w/bin/b" and result.prompts_asked == 1


def test_prose_steps_need_confirmation_and_refusal_is_no_plan():
    plan = BuildPlan(project_kind="compiled", steps=[st("build", "make", source=Source.PROSE, needs_confirm=True)])
    p, _, _ = make(FakeUI(), plan=plan, proposals=())
    p.run(opts())
    ui = FakeUI(prose=False)
    p, _, made = make(ui, plan=plan, proposals=())
    with pytest.raises(NoPlanError):
        p.run(opts())
    assert made == []


def test_local_folder_warns_output_written_in_place():
    ui = FakeUI()
    p, _, _ = make(ui, copy=WorkingCopy(path="/home/me/proj", in_place=True))
    p.run(opts())
    assert any("/home/me/proj" in w for w in ui.warnings)


def test_interpreted_in_container_commits_and_returns_launch_command():
    ui = FakeUI()
    plan = BuildPlan(
        project_kind="interpreted",
        steps=[st("setup", ["npm", "ci"]), st("launch", ["npm", "start"])],
    )
    p, runner, _ = make(ui, plan=plan, proposals=(), collected=Collected(launch=["npm", "start"]))
    result = p.run(opts())
    assert [s.kind for s in runner.ran] == ["setup"]
    assert "commit" in ui.events
    assert result.launch_command == "podman run recompt/abc npm start"


def test_linux_host_build_reports_missing_and_runs_no_installs():
    ui = FakeUI()
    p, runner, made = make(ui)
    p.run(opts(host_build=True))
    assert made[0]["host_build"] is True
    assert all(s.kind != "install" for s in runner.ran)
    assert any("cargo" in w for w in ui.warnings)


def test_claude_backend_gets_notice_before_sending():
    class Claude:
        name = "claude"
        model = "m"

        def extract_plan(self, sections):
            return "plan"

    ui = FakeUI()
    seen = {}
    p, _, _ = make(ui, llm=Claude())
    p.detect = lambda copy, ctx: seen.setdefault("llm", ctx.llm) and []
    p.run(opts(preview=True))
    assert seen["llm"].extract_plan([]) == "plan"
    assert ui.notices and "Claude" in ui.notices[0]
