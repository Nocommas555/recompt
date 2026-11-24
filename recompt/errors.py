class RecomptError(Exception):
    exit_code = 1

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BuildFailedError(RecomptError):
    exit_code = 1


class InvalidInputError(RecomptError):
    exit_code = 2


class DepsMissingError(RecomptError):
    exit_code = 3


class NoRunnableOutputError(RecomptError):
    exit_code = 4


class NoPlanError(RecomptError):
    exit_code = 5


class StepTimeoutError(RecomptError):
    exit_code = 6


class CancelledError(RecomptError):
    exit_code = 130
