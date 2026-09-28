from fastapi import APIRouter, Depends, HTTPException

from app.analysis.gates import GATE_DEFINITIONS
from app.api.dependencies import get_task_repository, get_validation_service
from app.models.api import GateInfo, KMapRequest, KMapResponse, TaskPreview, ValidateRequest, ValidateResponse
from app.models.task import Task
from app.services.task_repository import TaskRepository
from app.services.validation_service import ValidationService

router = APIRouter(prefix="/api/v1")


@router.post("/validate", response_model=ValidateResponse)
async def validate(
    request: ValidateRequest,
    service: ValidationService = Depends(get_validation_service),
    tasks: TaskRepository = Depends(get_task_repository),
) -> ValidateResponse:
    task = request.task
    if request.task_id is not None:
        task = tasks.get(request.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Unknown task '{request.task_id}'")
    assert task is not None
    return await service.validate(task, request.circuit, include_ai=request.include_ai, ai_mode=request.ai_mode)


@router.post("/kmap", response_model=KMapResponse)
def kmap(
    request: KMapRequest,
    service: ValidationService = Depends(get_validation_service),
    tasks: TaskRepository = Depends(get_task_repository),
) -> KMapResponse:
    """Karnaugh map of the target, or of the function the circuit computes (1-4 inputs)."""
    task = request.task
    if request.task_id is not None:
        task = tasks.get(request.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Unknown task '{request.task_id}'")
    assert task is not None
    return service.kmaps(task, request.circuit, request.source)


@router.get("/tasks", response_model=list[Task])
def list_tasks(tasks: TaskRepository = Depends(get_task_repository)) -> list[Task]:
    return tasks.list()


@router.post("/tasks/preview", response_model=TaskPreview)
def preview_task(task: Task, service: ValidationService = Depends(get_validation_service)) -> TaskPreview:
    """Show a user-defined target as both equations and a truth table, before any circuit exists."""
    return service.preview_task(task)


@router.get("/gates", response_model=list[GateInfo])
def list_gates() -> list[GateInfo]:
    return [
        GateInfo(type=d.type, min_inputs=d.min_inputs, max_inputs=d.max_inputs, default_inputs=d.default_inputs, description=d.description)
        for d in GATE_DEFINITIONS.values()
    ]
