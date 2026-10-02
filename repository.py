from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class AbstractRepository(ABC, Generic[T]):
    """Abstract base class for data repositories."""

    @abstractmethod
    def save(self, entity: T) -> T:
        """Persist an entity. Creates or updates."""
        ...

    @abstractmethod
    def get_by_id(self, entity_id: str) -> T | None:
        """Retrieve an entity by its ID. Returns None if not found."""
        ...

    @abstractmethod
    def list_all(self) -> list[T]:
        """Return all entities in the repository."""
        ...

    @abstractmethod
    def delete(self, entity_id: str) -> bool:
        """Delete an entity by ID. Returns True if deleted, False if not found."""
        ...
