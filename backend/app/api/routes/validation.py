from fastapi import APIRouter, Depends, HTTPException

from app.analysis.gates import GATE_DEFINITIONS
from app.api.dependencies import get_demo_matcher, get_generation_service, get_golden_repository, get_task_repository, get_validation_service
from app.models.api import DemoEntryOut, DemoMatchOut, DemoMatchRequest, DemoMatchResponse, GateInfo, GenerateRequest, GenerateResponse, GoldenCircuit, KMapRequest, KMapResponse, TaskPreview, ValidateRequest, ValidateResponse
from app.models.circuit import Circuit
from app.models.task import Task
from app.services.demo_matcher import DemoMatcher
from app.services.generation_service import GenerationService
from app.services.golden_repository import GoldenRepository
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


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    request: GenerateRequest,
    service: GenerationService = Depends(get_generation_service),
    tasks: TaskRepository = Depends(get_task_repository),
) -> GenerateResponse:
    """Build a circuit for an exercise: AI first (verified, with retries), stored circuit as the safety net."""
    task = request.task
    if request.intent == "describe":
        if not (request.prompt or "").strip():
            raise HTTPException(status_code=422, detail="Describe the circuit you want in the prompt.")
        task = None  # a plain-language request has no target
    else:
        if request.task_id is not None:
            task = tasks.get(request.task_id)
            if task is None:
                raise HTTPException(status_code=404, detail=f"Unknown task '{request.task_id}'")
        if task is None:
            raise HTTPException(status_code=422, detail="Give a task_id or a task.")
        if request.intent == "extend" and request.circuit is None:
            raise HTTPException(status_code=422, detail="Give the current circuit to build on.")
    result = await service.generate(task, request.prompt, request.mode, request.intent, request.circuit)
    return GenerateResponse(
        success=result.success, source=result.source,  # type: ignore[arg-type]
        circuit=Circuit.model_validate(result.circuit) if result.circuit else None,
        explanation=result.explanation, attempts=result.attempts, notice=result.notice, model=result.model,
        spec=Task.model_validate(result.spec) if result.spec else None, matched_task_id=result.matched_task_id,
    )


@router.get("/demo/catalog", response_model=list[DemoEntryOut])
def demo_catalog(matcher: DemoMatcher = Depends(get_demo_matcher)) -> list[DemoEntryOut]:
    """Every circuit demo mode can open, with whether it uses basic gates or an IC."""
    return [DemoEntryOut(task_id=e.task_id, title=e.title, style=e.style, parts=e.parts) for e in matcher.catalog()]  # type: ignore[arg-type]


@router.post("/demo/match", response_model=DemoMatchResponse)
def demo_match(request: DemoMatchRequest, matcher: DemoMatcher = Depends(get_demo_matcher)) -> DemoMatchResponse:
    """Map a request like "half adder" to a stored circuit. Deterministic text matching; the AI is never used."""
    matches = [DemoMatchOut(**vars(m)) for m in matcher.match(request.prompt, strict=request.strict)]
    best = matcher.best(request.prompt, strict=request.strict)
    return DemoMatchResponse(best=DemoMatchOut(**vars(best)) if best else None, matches=matches)


@router.get("/golden/{task_id}", response_model=GoldenCircuit)
def get_golden(task_id: str, golden: GoldenRepository = Depends(get_golden_repository)) -> GoldenCircuit:
    """The stored demo circuit for an exercise: loads instantly, with no AI and no network."""
    stored = golden.get(task_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"No demo circuit stored for '{task_id}'")
    return GoldenCircuit.model_validate(stored)


@router.get("/gates", response_model=list[GateInfo])
def list_gates() -> list[GateInfo]:
    return [
        GateInfo(type=d.type, min_inputs=d.min_inputs, max_inputs=d.max_inputs, default_inputs=d.default_inputs, description=d.description)
        for d in GATE_DEFINITIONS.values()
    ]
