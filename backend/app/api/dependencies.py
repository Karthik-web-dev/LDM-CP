from functools import lru_cache

from app.ai.client import create_ai_validator
from app.config import get_settings
from app.services.demo_matcher import DemoMatcher
from app.services.generation_service import GenerationService
from app.services.golden_repository import GoldenRepository
from app.services.task_repository import TaskRepository
from app.services.validation_service import ValidationService


@lru_cache
def get_validation_service() -> ValidationService:
    settings = get_settings()
    return ValidationService(create_ai_validator(settings), settings)


@lru_cache
def get_task_repository() -> TaskRepository:
    return TaskRepository()


@lru_cache
def get_generation_service() -> GenerationService:
    validation = get_validation_service()
    return GenerationService(validation.ai_validator, validation, get_golden_repository(), get_settings(), get_demo_matcher())


@lru_cache
def get_demo_matcher() -> DemoMatcher:
    return DemoMatcher(get_task_repository(), get_golden_repository())


@lru_cache
def get_golden_repository() -> GoldenRepository:
    return GoldenRepository()
