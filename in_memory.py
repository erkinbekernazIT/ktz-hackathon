from __future__ import annotations

from typing import Generic, TypeVar

from src.infrastructure.database.repository import AbstractRepository

T = TypeVar("T")


class InMemoryRepository(AbstractRepository[T], Generic[T]):
    """In-memory repository implementation for development and testing."""

    def __init__(self) -> None:
        self._store: dict[str, T] = {}

    def save(self, entity: T) -> T:
        entity_id = self._get_id(entity)
        self._store[entity_id] = entity
        return entity

    def get_by_id(self, entity_id: str) -> T | None:
        return self._store.get(entity_id)

    def list_all(self) -> list[T]:
        return list(self._store.values())

    def delete(self, entity_id: str) -> bool:
        if entity_id in self._store:
            del self._store[entity_id]
            return True
        return False

    def _get_id(self, entity: T) -> str:
        """Extract ID from entity. Tries .id attribute first, then str()."""
        if hasattr(entity, "id"):
            return str(getattr(entity, "id"))
        raise ValueError(f"Cannot determine ID for entity of type {type(entity)}")
