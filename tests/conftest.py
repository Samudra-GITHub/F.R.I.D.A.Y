"""Pytest configuration and shared fixtures for W.E.D.N.E.S.D.A.Y. test suite."""

import os
import sys
import tempfile
from pathlib import Path
import pytest

# Tests must not depend on the developer's .env.
os.environ["FRIDAY_SKIP_DOTENV"] = "1"

# Keep the API's persistent memory store out of the user's real ~/.friday during tests.
os.environ.setdefault(
    "FRIDAY_MEMORY_DB", str(Path(tempfile.mkdtemp(prefix="friday-test-")) / "memory.sqlite3")
)

# Same for location: tests must never start a real worker or touch the user's location state.
_location_dir = Path(tempfile.mkdtemp(prefix="friday-location-test-"))
os.environ["FRIDAY_LOCATION_STATE"] = str(_location_dir / "location_state.json")
os.environ["FRIDAY_LOCATION_LOCK"] = str(_location_dir / "location.lock")

# Ensure project root and backend are in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))


@pytest.fixture(autouse=True)
def default_test_settings(monkeypatch):
    """Ensure automated tests run in offline mode by default (zero live external API requests)."""
    from backend.friday.config import settings
    monkeypatch.setattr(settings, "location_provider", "none")


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Fixture providing a clean temporary workspace directory."""
    ws = tmp_path / "FridayWorkspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws
