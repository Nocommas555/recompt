import recompt
from recompt.cli import main


def test_package_imports():
    assert recompt.__version__


def test_cli_entry_point_returns_zero():
    assert main([]) == 0
