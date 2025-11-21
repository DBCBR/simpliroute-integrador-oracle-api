from typing import Generic, Iterable, List, Optional, TypeVar

T = TypeVar("T")


class InMemoryQueue(Generic[T]):
    """
    Fila em memória para exemplo.
    API mínima: enqueue(item), dequeue() -> Optional[item]
    """

    def __init__(self, items: Optional[Iterable[T]] = None) -> None:
        self._items: List[T] = list(items or [])

    def enqueue(self, item: T) -> None:
        self._items.append(item)

    def dequeue(self) -> Optional[T]:
        return self._items.pop(0) if self._items else None

    def __len__(self) -> int:
        return len(self._items)
