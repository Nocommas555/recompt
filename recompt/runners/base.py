from collections import deque
from typing import Callable, Protocol

from recompt.models import Step, StepResult

OutputCallback = Callable[[str], None]
TAIL_LINES = 40


class Runner(Protocol):
    def start(self) -> None: ...

    def run(self, step: Step) -> StepResult: ...

    def kill(self) -> None: ...

    def stop(self) -> None: ...


class OutputTail:
    def __init__(self, forward: OutputCallback):
        self.forward = forward
        self.lines: deque[str] = deque(maxlen=TAIL_LINES)

    def __call__(self, line: str) -> None:
        self.lines.append(line)
        self.forward(line)

    def text(self) -> str:
        return "\n".join(self.lines)
