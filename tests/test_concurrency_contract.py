import asyncio
import threading
import time
from pathlib import Path

from ghidra_mcp.registry import ToolDefinition, ToolRegistry


DESCRIPTION = """并发测试工具。

输入输出与副作用：输入程序会话；返回程序会话；只读或写入取决于注册标记。

何时使用：仅用于验证并发闸门；真实分析请使用任务工具。
"""


class ConcurrencyProbe:
    """记录工具函数同时处于活动状态的最大数量。"""

    def __init__(self, delay: float = 0.05) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0
        self.calls = 0
        self.delay = delay

    def __call__(self, program_id: str) -> str:
        with self._lock:
            self._active += 1
            self.calls += 1
            self.max_active = max(self.max_active, self._active)
        time.sleep(self.delay)
        with self._lock:
            self._active -= 1
        return program_id


def _register(registry: ToolRegistry, name: str, handler, *, mutates: bool) -> None:
    registry.register(ToolDefinition(name, DESCRIPTION, handler, mutates=mutates))


def test_program_gates_share_readers_and_serialize_the_writer() -> None:
    from ghidra_mcp.concurrency import ProgramGates

    gates = ProgramGates()
    entered = 0
    entered_lock = threading.Lock()
    readers_inside = threading.Event()
    proceed = threading.Event()
    order: list[str] = []

    def reader(tag: str) -> None:
        nonlocal entered
        with gates.shared("p"):
            with entered_lock:
                entered += 1
                if entered == 2:
                    readers_inside.set()
            order.append(f"read-{tag}-in")
            proceed.wait(timeout=5)
            order.append(f"read-{tag}-out")

    readers = [threading.Thread(target=reader, args=(str(i),)) for i in range(2)]
    for reader_thread in readers:
        reader_thread.start()
    assert readers_inside.wait(timeout=5) is True

    writer_entered = threading.Event()

    def writer() -> None:
        with gates.exclusive("p"):
            writer_entered.set()
            order.append("write")

    writer_thread = threading.Thread(target=writer)
    writer_thread.start()
    assert writer_entered.wait(timeout=0.2) is False

    proceed.set()
    for reader_thread in readers:
        reader_thread.join(timeout=5)
    writer_thread.join(timeout=5)

    assert writer_entered.is_set()
    assert order.index("write") > order.index("read-0-out")
    assert order.index("write") > order.index("read-1-out")


def test_executor_runs_shared_tools_concurrently() -> None:
    from ghidra_mcp.server import GhidraToolExecutor, create_mcp_app

    probe = ConcurrencyProbe()
    registry = ToolRegistry()
    _register(registry, "shared", probe, mutates=False)
    executor = GhidraToolExecutor(max_workers=4)
    app = create_mcp_app(registry, host="127.0.0.1", port=8765, tool_executor=executor)
    tool = app._tool_manager._tools["shared"]

    async def exercise() -> None:
        await asyncio.gather(*(tool.run({"program_id": "p"}) for _ in range(4)))

    try:
        asyncio.run(exercise())
    finally:
        executor.shutdown()

    assert probe.calls == 4
    assert probe.max_active > 1


def test_executor_serializes_mutating_tools_for_the_same_program() -> None:
    from ghidra_mcp.server import GhidraToolExecutor, create_mcp_app

    probe = ConcurrencyProbe()
    registry = ToolRegistry()
    _register(registry, "exclusive", probe, mutates=True)
    executor = GhidraToolExecutor(max_workers=4)
    app = create_mcp_app(registry, host="127.0.0.1", port=8765, tool_executor=executor)
    tool = app._tool_manager._tools["exclusive"]

    async def exercise() -> None:
        await asyncio.gather(*(tool.run({"program_id": "p"}) for _ in range(4)))

    try:
        asyncio.run(exercise())
    finally:
        executor.shutdown()

    assert probe.calls == 4
    assert probe.max_active == 1


def test_executor_runs_mutations_on_distinct_programs_in_parallel() -> None:
    from ghidra_mcp.server import GhidraToolExecutor, create_mcp_app

    probe = ConcurrencyProbe()
    registry = ToolRegistry()
    _register(registry, "exclusive", probe, mutates=True)
    executor = GhidraToolExecutor(max_workers=4)
    app = create_mcp_app(registry, host="127.0.0.1", port=8765, tool_executor=executor)
    tool = app._tool_manager._tools["exclusive"]

    async def exercise() -> None:
        await asyncio.gather(
            *(tool.run({"program_id": f"p{index}"}) for index in range(4))
        )

    try:
        asyncio.run(exercise())
    finally:
        executor.shutdown()

    assert probe.calls == 4
    assert probe.max_active > 1


def test_one_worker_executor_keeps_a_single_thread() -> None:
    from ghidra_mcp.server import GhidraToolExecutor, create_mcp_app

    registry = ToolRegistry()
    worker_threads: list[int] = []

    def record(program_id: str) -> str:
        worker_threads.append(threading.get_ident())
        return program_id

    _register(registry, "shared", record, mutates=False)
    executor = GhidraToolExecutor()
    app = create_mcp_app(registry, host="127.0.0.1", port=8765, tool_executor=executor)
    tool = app._tool_manager._tools["shared"]

    try:
        asyncio.run(tool.run({"program_id": "p"}))
    finally:
        executor.shutdown()

    assert len(set(worker_threads)) == 1


def test_default_resource_namer_keys_program_and_binary_calls() -> None:
    from ghidra_mcp.server import _default_resource_namer

    assert _default_resource_namer({"program_id": "abc"}) == "program:abc"
    assert _default_resource_namer({"text": "x"}) is None
    assert (
        _default_resource_namer({"binary_path": "data/sample.bin"})
        == f"binary:{(Path('data/sample.bin')).resolve()}"
    )
