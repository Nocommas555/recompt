import io
import tempfile
from pathlib import Path

import pytest

from recompt import errors
from recompt.cli import TerminalUI, main, parse_args
from recompt.models import InstallProposal, RunResult, Source, Step


def ui(tty=True, answers=()):
    answers = list(answers)
    out, err = io.StringIO(), io.StringIO()
    t = TerminalUI(out=out, err=err, is_tty=lambda: tty, ask=lambda prompt: answers.pop(0), log=None)
    return t, out, err


PROSE = [Step(kind="build", command="make", source=Source.PROSE, needs_confirm=True, origin="README.md")]
APT = [InstallProposal(manager="brew", packages=["cmake"])]


def test_prose_needs_interactive_yes():
    t, out, _ = ui(answers=["y"])
    assert t.confirm_prose(PROSE) is True
    assert "make" in out.getvalue()
    t, _, _ = ui(answers=["n"])
    assert t.confirm_prose(PROSE) is False


def test_prose_refused_without_terminal():
    t, _, err = ui(tty=False)
    assert t.confirm_prose(PROSE) is False
    assert "terminal" in err.getvalue()


def test_install_confirmation_and_default_no():
    t, out, _ = ui(answers=[""])
    assert t.confirm_installs(APT) is False
    assert "cmake" in out.getvalue()
    t, _, _ = ui(answers=["yes"])
    assert t.confirm_installs(APT) is True


def test_installs_refused_without_terminal():
    t, _, err = ui(tty=False)
    assert t.confirm_installs(APT) is False
    assert "--yes" in err.getvalue()


def test_choose_by_number_and_first_without_terminal():
    t, _, _ = ui(answers=["2"])
    assert t.choose("Which?", ["a", "b"]) == "b"
    t, _, err = ui(tty=False)
    assert t.choose("Which?", ["a", "b"]) == "a"
    assert "a" in err.getvalue()


def test_arguments_are_parsed():
    a = parse_args(["https://x/r", "--ref", "v1", "--preview", "--host-build", "--timeout", "60", "--llm", "ollama", "--yes"])
    assert (a.source, a.ref, a.preview, a.host_build, a.timeout, a.llm, a.yes) == (
        "https://x/r", "v1", True, True, 60, "ollama", True,
    )
    d = parse_args(["."])
    assert (d.ref, d.preview, d.host_build, d.timeout, d.llm, d.yes) == (None, False, False, None, None, False)


class FakePipeline:
    def __init__(self, behaviour):
        self.behaviour, self.opts = behaviour, None

    def run(self, opts):
        self.opts = opts
        return self.behaviour()


def run_main(behaviour, argv=("https://x/r",)):
    out, err = io.StringIO(), io.StringIO()
    made = {}

    def make_pipeline(ui, host_os, llm):
        made["p"] = FakePipeline(behaviour)
        return made["p"]

    log_dir = Path(tempfile.mkdtemp())
    code = main(list(argv), make_pipeline=make_pipeline, out=out, err=err, is_tty=lambda: False, log_dir=log_dir)
    return code, out.getvalue() + err.getvalue(), made["p"]


def test_success_exits_zero_and_passes_options():
    code, text, p = run_main(lambda: RunResult(status="ok", program_path="/w/tool"), ["src", "--timeout", "5"])
    assert code == 0 and "/w/tool" in text
    assert p.opts.source == "src" and p.opts.timeout == 5


def test_default_timeout_comes_from_config():
    _, _, p = run_main(lambda: RunResult(status="ok", program_path="/w/tool"))
    assert p.opts.timeout == 1800


@pytest.mark.parametrize(
    "cls, code",
    [
        (errors.BuildFailedError, 1),
        (errors.InvalidInputError, 2),
        (errors.DepsMissingError, 3),
        (errors.NoRunnableOutputError, 4),
        (errors.NoPlanError, 5),
        (errors.StepTimeoutError, 6),
        (errors.CancelledError, 130),
    ],
)
def test_each_error_maps_to_its_exit_code(cls, code):
    def fail():
        exc = cls("went wrong")
        exc.result = RunResult(status="build_failed")
        raise exc

    got, text, _ = run_main(fail)
    assert got == code and "went wrong" in text


def test_ctrl_c_outside_a_step_exits_130():
    def interrupt():
        raise KeyboardInterrupt

    code, text, _ = run_main(interrupt)
    assert code == 130 and "Cancelled" in text


def test_help_exits_cleanly():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
