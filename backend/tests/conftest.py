import os

import pytest

from app.config import Limits, Settings


@pytest.fixture(autouse=True)
def hermetic_settings(monkeypatch):
    """Keep tests independent of the developer's backend/.env and AI_* / LIMIT_* environment variables."""
    for name in list(os.environ):
        if name.upper().startswith(("AI_", "LIMIT_")):
            monkeypatch.delenv(name)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setitem(Limits.model_config, "env_file", None)
