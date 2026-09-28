from functools import lru_cache

from app.ai.client import create_ai_validator
from app.config import get_settings
from app.services.task_repository import TaskRepository
from app.services.validation_service import ValidationService


@lru_cache
def get_validation_service() -> ValidationService:
    settings = get_settings()
    return ValidationService(create_ai_validator(settings), settings)


@lru_cache
def get_task_repository() -> TaskRepository:
    return TaskRepository()
