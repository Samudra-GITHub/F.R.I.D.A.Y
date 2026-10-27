"""Pytest configuration and shared fixtures for F.R.I.D.A.Y. test suite."""

import sys
from pathlib import Path
import pytest

# Ensure project root and backend are in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Fixture providing a clean temporary workspace directory."""
    ws = tmp_path / "FridayWorkspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws
