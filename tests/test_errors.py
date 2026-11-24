import pytest

from recompt import errors

EXPECTED = [
    (errors.BuildFailedError, 1),
    (errors.InvalidInputError, 2),
    (errors.DepsMissingError, 3),
    (errors.NoRunnableOutputError, 4),
    (errors.NoPlanError, 5),
    (errors.StepTimeoutError, 6),
    (errors.CancelledError, 130),
]


@pytest.mark.parametrize("cls, code", EXPECTED)
def test_each_error_carries_its_exit_code_and_message(cls, code):
    err = cls("something went wrong")
    assert isinstance(err, errors.RecomptError)
    assert err.exit_code == code
    assert err.message == "something went wrong"
    assert str(err) == "something went wrong"


def test_exit_codes_are_unique():
    codes = [code for _, code in EXPECTED]
    assert len(codes) == len(set(codes))
