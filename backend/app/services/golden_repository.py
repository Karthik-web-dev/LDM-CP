"""Stored, verified circuits for the built-in exercises (used by the demo mode and as an AI fallback).

One JSON file per exercise in ``app/data/golden``::

    { "task_id": "...", "title": "...", "source": "reference", "circuit": { ...normalized circuit... } }

The circuits are built by ``app.tools.build_golden``. The backtest (``python -m app.tools.backtest``) proves every stored circuit still passes its exercise.
"""

import json
from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "data" / "golden"


class GoldenRepository:
    def __init__(self, directory: Path = GOLDEN_DIR):
        self.directory = directory

    def _path(self, task_id: str) -> Path:
        # Task ids are validated identifiers, but never build a path from one without checking.
        if not task_id.replace("_", "").replace("-", "").isalnum():
            raise KeyError(task_id)
        return self.directory / f"{task_id}.json"

    def ids(self) -> list[str]:
        return sorted(p.stem for p in self.directory.glob("*.json")) if self.directory.exists() else []

    def get(self, task_id: str) -> dict | None:
        try:
            path = self._path(task_id)
        except KeyError:
            return None
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

