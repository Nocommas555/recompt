import argparse
import sys
import uuid
from pathlib import Path
from typing import Callable, TextIO

from platformdirs import user_log_path

from recompt import errors
from recompt.config import load_config
from recompt.llm import select_backend
from recompt.models import InstallProposal, RunResult, Step
from recompt.proc import current_os
from recompt.report import RunLog, command_text, format_plan, format_result

YES = {"y", "yes"}


class TerminalUI:
    def __init__(
        self,
        *,
        out: TextIO = sys.stdout,
        err: TextIO = sys.stderr,
        is_tty: Callable[[], bool] = sys.stdin.isatty,
        ask: Callable[[str], str] = input,
        log: RunLog | None = None,
    ):
        self.out, self.err, self.is_tty, self.ask, self.log = out, err, is_tty, ask, log

    def _print(self, text: str, stream: TextIO | None = None) -> None:
        print(text, file=stream or self.out, flush=True)
        if self.log:
            self.log.line(text)

    def warn(self, msg: str) -> None:
        self._print(f"warning: {msg}", self.err)

    def notice(self, msg: str) -> None:
        self._print(f"note: {msg}", self.err)

    def show_plan(self, plan, proposals: list[InstallProposal]) -> None:
        self._print(format_plan(plan, proposals))

    def _yes(self, question: str) -> bool:
        return self.ask(f"{question} [y/N] ").strip().lower() in YES

    def confirm_installs(self, proposals: list[InstallProposal]) -> bool:
        self._print("Missing dependencies:")
        for p in proposals:
            self._print(f"  {p.manager}: {' '.join(p.packages)}")
            for step in p.commands:
                self._print(f"  will run: {command_text(step.command)}")
        if not self.is_tty():
            self.warn("Installing dependencies needs confirmation; run in a terminal or pass --yes")
            return False
        return self._yes("Install these dependencies?")

    def confirm_prose(self, steps: list[Step]) -> bool:
        self._print("These steps were read from README text and need your OK:")
        for step in steps:
            self._print(f"  {command_text(step.command)}   (from {step.origin})")
        if not self.is_tty():
            self.warn("Steps from README text need confirmation in an interactive terminal; --yes does not cover them")
            return False
        return self._yes("Run these steps?")

    def choose(self, prompt: str, options: list[str]) -> str:
        if not self.is_tty():
            self.warn(f"{prompt} No terminal to ask, using {options[0]}")
            return options[0]
        self._print(prompt)
        for n, option in enumerate(options, 1):
            self._print(f"  {n}) {option}")
        while True:
            answer = self.ask("Number: ").strip()
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return options[int(answer) - 1]

    def step_started(self, step: Step) -> None:
        if self.log:
            self.log.command(step)
        print(f"==> {command_text(step.command).splitlines()[0]}", file=self.out, flush=True)

    def output(self, line: str) -> None:
        print(line, file=self.out, flush=True)
        if self.log:
            self.log.line(line)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="recompt", description="Find a project's build instructions and build it.")
    parser.add_argument("source", help="git URL, GitHub link, or local folder")
    parser.add_argument("--ref", help="branch, tag or commit to build")
    parser.add_argument("--preview", action="store_true", help="print the plan and run nothing")
    parser.add_argument("--host-build", action="store_true", help="on Linux, build on the host without a container")
    parser.add_argument("--timeout", type=int, help="time limit per step in seconds")
    parser.add_argument("--llm", choices=["auto", "claude", "ollama", "none"], help="backend for README instructions")
    parser.add_argument("--yes", action="store_true", help="install missing dependencies without asking")
    return parser.parse_args(argv)


def _default_pipeline(ui, host_os, llm):
    from recompt.pipeline import Pipeline

    return Pipeline(ui, host_os=host_os, llm=llm)


def main(
    argv: list[str] | None = None,
    *,
    make_pipeline=_default_pipeline,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
    is_tty: Callable[[], bool] = sys.stdin.isatty,
    ask: Callable[[str], str] = input,
    log_dir: Path | None = None,
) -> int:
    from recompt.pipeline import RunOptions

    args = parse_args(argv)
    run_id = uuid.uuid4().hex[:8]
    log = RunLog((log_dir or user_log_path("recompt")) / f"run-{run_id}.log")
    ui = TerminalUI(out=out, err=err, is_tty=is_tty, ask=ask, log=log)
    result: RunResult | None = None
    try:
        cfg = load_config()
        if args.llm:
            cfg.llm.backend = args.llm
        pipeline = make_pipeline(ui, current_os(), select_backend(cfg.llm))
        options = RunOptions(
            source=args.source, ref=args.ref, preview=args.preview, host_build=args.host_build,
            timeout=args.timeout or cfg.step_timeout, yes=args.yes,
        )
        result = pipeline.run(options)
        code = 0
    except errors.RecomptError as exc:
        ui._print(f"recompt: {exc.message}", err)
        result = getattr(exc, "result", None)
        code = exc.exit_code
    except KeyboardInterrupt:
        ui._print("recompt: Cancelled", err)
        code = errors.CancelledError.exit_code
    finally:
        log.close()
    if result is not None and not (args.preview and code == 0):
        result.log_path = str(log.path)
        print(format_result(result), file=out if code == 0 else err, flush=True)
    return code
