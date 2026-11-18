"""Prove that every stored circuit still passes its exercise. Run before a demo.

    cd backend && ../venv/Scripts/python.exe -m app.tools.backtest

Each golden circuit goes through the same deterministic analysis as a student's circuit (no AI, no
network). Exits with status 1 if any exercise has no circuit or its circuit fails.
"""

import sys
import time
from dataclasses import dataclass

from app.ai.client import MockAIValidator
from app.config import Settings
from app.models.circuit import Circuit
from app.services.golden_repository import GoldenRepository
from app.services.task_repository import TaskRepository
from app.services.validation_service import ValidationService


@dataclass
class BacktestRow:
    task_id: str
    title: str
    ok: bool
    detail: str
    seconds: float


def run_backtest(repo: GoldenRepository | None = None) -> list[BacktestRow]:
    repo = repo or GoldenRepository()
    service = ValidationService(MockAIValidator(), Settings(ai_provider="mock"))
    rows: list[BacktestRow] = []
    for task in TaskRepository().list():
        started = time.perf_counter()
        stored = repo.get(task.id)
        if stored is None:
            rows.append(BacktestRow(task.id, task.title, False, "no golden circuit stored", 0.0))
            continue
        try:
            circuit = Circuit.model_validate(stored["circuit"])
            det = service.analyze(task, circuit)
        except Exception as exc:  # a corrupt file must show up as a failure, not crash the run
            rows.append(BacktestRow(task.id, task.title, False, f"could not analyse: {exc}", time.perf_counter() - started))
            continue
        passed = det.structurally_valid and not det.errors and det.equivalent_to_expected
        if passed:
            detail = f"{len(circuit.gates)} parts, {stored.get('source', '?')}"
        elif det.errors:
            detail = det.errors[0].message
        else:
            detail = "analysis ran but the circuit does not match the target"
        rows.append(BacktestRow(task.id, task.title, passed, detail, time.perf_counter() - started))
    return rows


def main() -> int:
    rows = run_backtest()
    width = max(len(r.task_id) for r in rows)
    for r in rows:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.task_id:<{width}}  {r.seconds * 1000:6.0f} ms  {r.detail}")
    failed = [r for r in rows if not r.ok]
    print(f"\n{len(rows) - len(failed)}/{len(rows)} exercises pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
