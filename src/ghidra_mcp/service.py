"""完整 MCP 服务对象的装配与退出清理。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .catalog import build_default_registry
from .config import (
    ConfigurationError,
    Settings,
    normalize_http_public_url,
    validate_http_auth_token,
)
from .runtime import GhidraRuntime, ProgramWorkspace
from .server import GhidraToolExecutor, create_mcp_app


@dataclass(slots=True)
class MCPService:
    settings: Settings
    app: FastMCP
    workspace: ProgramWorkspace
    tool_executor: GhidraToolExecutor

    def run(self) -> None:
        try:
            self.app.run(transport=self.settings.transport)  # type: ignore[arg-type]
        finally:
            try:
                self.tool_executor.run_sync(self.workspace.close_all)
            finally:
                self.tool_executor.shutdown()


def create_service(settings: Settings, *, pyghidra_module: Any | None = None) -> MCPService:
    if settings.install_dir is None:
        raise ConfigurationError("必须通过 GHIDRA_INSTALL_DIR 或 TOML 配置 Ghidra 安装目录")
    public_url = None
    if settings.transport == "streamable-http":
        validate_http_auth_token(settings.auth_token)
        public_url = normalize_http_public_url(settings.public_url)
    if settings.transport == "streamable-http" and settings.input_root is None:
        raise ConfigurationError("streamable-http 必须设置 GHIDRA_MCP_INPUT_ROOT")
    runtime = GhidraRuntime(
        settings.install_dir,
        pyghidra_module=pyghidra_module,
        analysis_timeout_seconds=settings.analysis_timeout_seconds,
    )
    workspace = ProgramWorkspace(
        runtime,
        project_location=settings.storage_root,
        input_root=settings.input_root,
    )
    def resource_namer(arguments: dict[str, Any]) -> str | None:
        if "program_id" in arguments:
            return workspace.resource_key(str(arguments["program_id"]))
        if "binary_path" in arguments:
            return str(Path(str(arguments["binary_path"])).resolve())
        return None

    registry = build_default_registry(workspace)
    tool_executor = GhidraToolExecutor(max_workers=settings.max_workers)
    app = create_mcp_app(
        registry,
        host=settings.host,
        port=settings.port,
        auth_token=settings.auth_token if settings.transport == "streamable-http" else None,
        public_url=public_url,
        tool_executor=tool_executor,
        resource_namer=resource_namer,
    )
    return MCPService(
        settings=settings,
        app=app,
        workspace=workspace,
        tool_executor=tool_executor,
    )
