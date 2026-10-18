"""把本地工具注册表绑定到 FastMCP。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial, wraps
from hashlib import sha256
import hmac
from importlib.metadata import PackageNotFoundError, version as package_version
import inspect
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .concurrency import ProgramGates
from .registry import ToolDefinition, ToolRegistry


def _default_resource_namer(arguments: dict[str, Any]) -> str | None:
    """按 program_id 或 binary_path 推导程序资源键；非程序工具返回 None。"""

    if "program_id" in arguments:
        return f"program:{arguments['program_id']}"
    if "binary_path" in arguments:
        return f"binary:{Path(arguments['binary_path']).resolve()}"
    return None


class GhidraToolExecutor:
    """在固定 worker 池上运行 JVM 工具，并按程序串行写、并行读。"""

    def __init__(self, max_workers: int = 1, *, gates: ProgramGates | None = None) -> None:
        if max_workers < 1:
            raise ValueError("max_workers 必须大于等于 1")
        self.max_workers = max_workers
        self._gates = gates if gates is not None else ProgramGates()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="ghidra-mcp"
        )

    async def run(
        self,
        function: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        resource: str | None = None,
        exclusive: bool = False,
    ) -> Any:
        loop = asyncio.get_running_loop()
        call = partial(function, *args, **kwargs)
        if resource is None:
            return await loop.run_in_executor(self._executor, call)
        runner = partial(self._guarded, call, resource, exclusive)
        return await loop.run_in_executor(self._executor, runner)

    def _guarded(self, call: Any, resource: str, exclusive: bool) -> Any:
        gate = self._gates.exclusive if exclusive else self._gates.shared
        with gate(resource):
            return call()

    def run_sync(self, function: Any, *args: Any, **kwargs: Any) -> Any:
        return self._executor.submit(function, *args, **kwargs).result()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)


def _async_handler(
    tool: ToolDefinition, executor: GhidraToolExecutor, resource_namer: Any
) -> Any:
    @wraps(tool.handler)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        return await executor.run(
            tool.handler,
            args,
            kwargs,
            resource=resource_namer(kwargs),
            exclusive=tool.mutates,
        )

    return wrapped


class StaticTokenVerifier(TokenVerifier):
    """验证部署者通过环境变量提供的单一 Bearer token。"""

    def __init__(self, expected_token: str) -> None:
        self._expected_token = expected_token.encode("utf-8")

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token.encode("utf-8"), self._expected_token):
            return None
        return AccessToken(
            token=token,
            client_id="ghidra-mcp",
            scopes=["mcp"],
            subject="configured-client",
        )


def _schema_version(registry: ToolRegistry) -> str:
    contracts = [
        {
            "name": tool.name,
            "description": tool.description,
            "signature": str(inspect.signature(tool.handler)),
            "contract_version": tool.contract_version,
            "annotations": (
                tool.annotations.model_dump(exclude_none=True)
                if tool.annotations is not None
                else None
            ),
        }
        for tool in registry.enabled_tools()
    ]
    encoded = json.dumps(contracts, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return sha256(encoded).hexdigest()[:16]


def _runtime_version() -> str:
    try:
        return package_version("ghidra-mcp")
    except PackageNotFoundError:
        return "unknown"


def _git_commit() -> str:
    configured = os.environ.get("GHIDRA_MCP_GIT_COMMIT", "").strip()
    if configured:
        return configured
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def create_mcp_app(
    registry: ToolRegistry,
    *,
    host: str,
    port: int,
    auth_token: str | None = None,
    public_url: str | None = None,
    version: str | None = None,
    git_commit: str | None = None,
    tool_executor: GhidraToolExecutor | None = None,
    max_workers: int = 1,
    resource_namer: Any = None,
) -> FastMCP:
    auth = None
    verifier = None
    if auth_token is not None:
        if public_url is None:
            raise ValueError("启用 HTTP 鉴权时必须提供 public_url")
        base_url = public_url.rstrip("/")
        auth = AuthSettings(
            issuer_url=base_url,
            resource_server_url=f"{base_url}/mcp",
            required_scopes=["mcp"],
        )
        verifier = StaticTokenVerifier(auth_token)
    app = FastMCP(
        "ghidra-mcp",
        host=host,
        port=port,
        auth=auth,
        token_verifier=verifier,
    )
    executor = tool_executor or GhidraToolExecutor(max_workers=max_workers)
    namer = resource_namer or _default_resource_namer
    for tool in registry.enabled_tools():
        app.tool(
            name=tool.name,
            description=tool.description,
            annotations=tool.annotations,
        )(_async_handler(tool, executor, namer))

    health_payload = {
        "status": "ok",
        "version": version or _runtime_version(),
        "git_commit": git_commit or _git_commit(),
        "schema_version": _schema_version(registry),
    }

    @app.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> Response:
        return JSONResponse(health_payload)

    return app
