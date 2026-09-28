"""Built-in exercises, loaded from app/data/tasks.json."""

import json
from pathlib import Path

from app.models.task import Task

TASKS_FILE = Path(__file__).resolve().parent.parent / "data" / "tasks.json"


class TaskRepository:
    def __init__(self, path: Path = TASKS_FILE):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._tasks = {t.id: t for t in (Task.model_validate(item) for item in raw)}

    def list(self) -> list[Task]:
        return list(self._tasks.values())

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)
