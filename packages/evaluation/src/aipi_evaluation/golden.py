"""Compatibility oracle used by golden tests; only the scorer opens hidden labels."""

from pathlib import Path

from aipi_evaluation.oracle import load_truth


def expected_category(path: Path) -> str:
    return load_truth(path).expected_category
