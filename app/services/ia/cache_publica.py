"""LRU acotada exclusivamente para explicaciones de normativa pública validada."""
from collections import OrderedDict
from threading import Lock
from time import monotonic


class CachePublica:
    def __init__(self):
        self._items = OrderedDict()
        self._lock = Lock()

    def obtener(self, key, ttl, capacidad):
        if ttl <= 0 or capacidad <= 0:
            return None
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            created, value = item
            if monotonic()-created >= ttl:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return value.model_copy(deep=True)

    def guardar(self, key, value, capacidad):
        if capacidad <= 0:
            return
        with self._lock:
            self._items[key] = (monotonic(), value.model_copy(deep=True))
            self._items.move_to_end(key)
            while len(self._items) > capacidad:
                self._items.popitem(last=False)


explicaciones = CachePublica()
