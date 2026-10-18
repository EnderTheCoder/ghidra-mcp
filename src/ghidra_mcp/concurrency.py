"""跨 MCP 调用的程序级共享读 / 独占写闸门。

Ghidra 的 ProgramDB 允许并发读取，但任何事务写入都必须在没有其它读写者时进行。
每个程序资源对应一个闸门：多个只读调用共享进入，写调用独占进入。
"""

from __future__ import annotations

from contextlib import contextmanager
from threading import Condition, Lock
from typing import Iterator


class ProgramGates:
    """按资源键维护共享读、独占写闸门。"""

    def __init__(self) -> None:
        self._guard = Lock()
        self._gates: dict[str, _Gate] = {}

    @contextmanager
    def shared(self, key: str) -> Iterator[None]:
        gate = self._gate(key)
        gate.acquire_shared()
        try:
            yield
        finally:
            gate.release_shared()

    @contextmanager
    def exclusive(self, key: str) -> Iterator[None]:
        gate = self._gate(key)
        gate.acquire_exclusive()
        try:
            yield
        finally:
            gate.release_exclusive()

    def _gate(self, key: str) -> "_Gate":
        with self._guard:
            gate = self._gates.get(key)
            if gate is None:
                gate = _Gate()
                self._gates[key] = gate
            return gate


class _Gate:
    def __init__(self) -> None:
        self._condition = Condition()
        self._readers = 0
        self._writer = False

    def acquire_shared(self) -> None:
        with self._condition:
            while self._writer:
                self._condition.wait()
            self._readers += 1

    def release_shared(self) -> None:
        with self._condition:
            self._readers -= 1
            if self._readers == 0:
                self._condition.notify_all()

    def acquire_exclusive(self) -> None:
        with self._condition:
            while self._writer or self._readers:
                self._condition.wait()
            self._writer = True

    def release_exclusive(self) -> None:
        with self._condition:
            self._writer = False
            self._condition.notify_all()
