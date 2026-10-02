"""Small observable caches; callers own keys and invalidation boundaries."""

from collections import OrderedDict
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class LRU(Generic[K, V]):
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.values: OrderedDict[K, V] = OrderedDict()
        self.hits = self.misses = 0

    def get(self, key: K) -> tuple[bool, V | None]:
        if key not in self.values:
            self.misses += 1
            return False, None
        self.hits += 1
        self.values.move_to_end(key)
        return True, self.values[key]

    def put(self, key: K, value: V) -> None:
        self.values[key] = value
        self.values.move_to_end(key)
        while len(self.values) > self.capacity:
            self.values.popitem(last=False)

    def clear(self) -> None:
        self.values.clear()

    def stats(self) -> dict:
        return dict(hits=self.hits, misses=self.misses, size=len(self.values), capacity=self.capacity)
