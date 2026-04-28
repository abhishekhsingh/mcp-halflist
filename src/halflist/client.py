from __future__ import annotations

import os
import shlex
import time
from contextlib import AsyncExitStack
from typing import Any

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from halflist.models import ServerInfo


class HalflistClient:
    def __init__(self, timeout: int = 30, quiet: bool = False) -> None:
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._timeout = timeout
        self._quiet = quiet
        self.init_result: types.InitializeResult | None = None

    async def connect_stdio(self, command: str) -> None:
        parts = shlex.split(command)
        server_params = StdioServerParameters(command=parts[0], args=parts[1:])

        self._exit_stack = AsyncExitStack()

        errlog: Any
        if self._quiet:
            errlog = open(os.devnull, "w")  # noqa: SIM115
            self._exit_stack.callback(errlog.close)
        else:
            errlog = None

        kwargs: dict[str, Any] = {"server": server_params}
        if errlog is not None:
            kwargs["errlog"] = errlog

        read_stream, write_stream = await self._exit_stack.enter_async_context(
            stdio_client(**kwargs)
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("Client not connected")
        return self._session

    async def initialize(self) -> ServerInfo:
        start = time.monotonic()
        result = await self.session.initialize()
        self._last_duration_ms = (time.monotonic() - start) * 1000
        self.init_result = result
        return ServerInfo(name=result.serverInfo.name, version=result.serverInfo.version)

    async def list_tools(self) -> list[types.Tool]:
        start = time.monotonic()
        result = await self.session.list_tools()
        self._last_duration_ms = (time.monotonic() - start) * 1000
        return result.tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> types.CallToolResult:
        start = time.monotonic()
        result = await self.session.call_tool(name, arguments)
        self._last_duration_ms = (time.monotonic() - start) * 1000
        return result

    async def ping(self) -> bool:
        start = time.monotonic()
        try:
            await self.session.send_ping()
            self._last_duration_ms = (time.monotonic() - start) * 1000
            return True
        except Exception:
            self._last_duration_ms = (time.monotonic() - start) * 1000
            return False

    async def close(self) -> None:
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except (RuntimeError, OSError, Exception):
                pass
            self._exit_stack = None
        self._session = None
