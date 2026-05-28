from __future__ import annotations

import asyncio
import os
import shlex
import time
from contextlib import AsyncExitStack
from typing import Any

import httpx
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from halflist.constants import DEFAULT_TIMEOUT
from halflist.debug import MCPDebugLogger, _format_args, create_debug_event_hooks
from halflist.models import ServerInfo


class HalflistClient:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT, quiet: bool = False) -> None:
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._timeout = timeout
        self._quiet = quiet
        self.init_result: types.InitializeResult | None = None
        self.transport: str = "stdio"
        self._last_duration_ms: float = 0.0

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
        self.transport = "stdio"

    async def connect_http(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        auth: httpx.Auth | None = None,
    ) -> None:
        """Connect via Streamable HTTP, falling back to legacy SSE.

        Each transport is verified by actually calling initialize().
        If Streamable HTTP fails or times out, we clean up and try SSE.
        When OAuth PKCE auth is active, the initialize timeout is extended
        to allow the browser-based flow to complete.
        """
        init_timeout = 300 if auth else self._timeout
        streamable_err: BaseException | None = None
        try:
            await self._try_streamable_http(url, headers, auth, init_timeout)
            self.transport = "streamable-http"
            return
        except BaseException as e:
            streamable_err = e

        try:
            await self._try_sse(url, headers, auth, init_timeout)
            self.transport = "sse"
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect via Streamable HTTP ({streamable_err}) and SSE ({e})"
            ) from e

    async def _try_streamable_http(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        auth: httpx.Auth | None = None,
        init_timeout: float | None = None,
    ) -> None:
        from mcp.client.streamable_http import streamable_http_client

        exit_stack = AsyncExitStack()
        try:
            http_client: httpx.AsyncClient | None = None
            hooks = create_debug_event_hooks()
            if headers or auth or hooks:
                kwargs: dict[str, Any] = {}
                if headers:
                    kwargs["headers"] = headers
                if auth:
                    kwargs["auth"] = auth
                if hooks:
                    kwargs["event_hooks"] = hooks
                http_client = httpx.AsyncClient(**kwargs)
                exit_stack.push_async_callback(http_client.aclose)

            ctx_args: dict[str, Any] = {"url": url}
            if http_client:
                ctx_args["http_client"] = http_client

            read_stream, write_stream, _ = await exit_stack.enter_async_context(
                streamable_http_client(**ctx_args)
            )
            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            timeout = init_timeout if init_timeout is not None else self._timeout
            result = await asyncio.wait_for(
                session.initialize(), timeout=timeout,
            )

            self._exit_stack = exit_stack
            self._session = session
            self.init_result = result
        except BaseException:
            self._session = None
            try:
                await exit_stack.aclose()
            except Exception:
                pass
            raise

    async def _try_sse(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        auth: httpx.Auth | None = None,
        init_timeout: float | None = None,
    ) -> None:
        from mcp.client.sse import sse_client

        exit_stack = AsyncExitStack()
        try:
            ctx_args: dict[str, Any] = {"url": url}
            if headers:
                ctx_args["headers"] = headers
            if auth:
                ctx_args["auth"] = auth

            read_stream, write_stream = await exit_stack.enter_async_context(
                sse_client(**ctx_args)
            )
            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            timeout = init_timeout if init_timeout is not None else self._timeout
            result = await asyncio.wait_for(
                session.initialize(), timeout=timeout,
            )

            self._exit_stack = exit_stack
            self._session = session
            self.init_result = result
        except BaseException:
            self._session = None
            try:
                await exit_stack.aclose()
            except Exception:
                pass
            raise

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("Client not connected")
        return self._session

    async def initialize(self) -> ServerInfo:
        if self.init_result is not None:
            return ServerInfo(
                name=self.init_result.serverInfo.name,
                version=self.init_result.serverInfo.version,
            )
        with MCPDebugLogger("initialize") as dbg:
            start = time.monotonic()
            result = await self.session.initialize()
            self._last_duration_ms = (time.monotonic() - start) * 1000
            self.init_result = result
            dbg.success(f"{result.serverInfo.name} v{result.serverInfo.version}")
        return ServerInfo(name=result.serverInfo.name, version=result.serverInfo.version)

    def has_capability(self, name: str) -> bool:
        if self.init_result is None or self.init_result.capabilities is None:
            return False
        return getattr(self.init_result.capabilities, name, None) is not None

    async def list_tools(self) -> list[types.Tool]:
        with MCPDebugLogger("tools/list") as dbg:
            start = time.monotonic()
            result = await self.session.list_tools()
            self._last_duration_ms = (time.monotonic() - start) * 1000
            dbg.success(f"{len(result.tools)} tools")
        return result.tools

    async def list_resources(self) -> list[types.Resource]:
        with MCPDebugLogger("resources/list") as dbg:
            start = time.monotonic()
            result = await self.session.list_resources()
            self._last_duration_ms = (time.monotonic() - start) * 1000
            dbg.success(f"{len(result.resources)} resources")
        return result.resources

    async def read_resource(self, uri: str) -> types.ReadResourceResult:
        from pydantic import AnyUrl

        with MCPDebugLogger("resources/read", uri) as dbg:
            start = time.monotonic()
            result = await self.session.read_resource(AnyUrl(uri))
            self._last_duration_ms = (time.monotonic() - start) * 1000
            count = len(result.contents) if result.contents else 0
            dbg.success(f"ok ({count} content items)")
        return result

    async def list_prompts(self) -> list[types.Prompt]:
        with MCPDebugLogger("prompts/list") as dbg:
            start = time.monotonic()
            result = await self.session.list_prompts()
            self._last_duration_ms = (time.monotonic() - start) * 1000
            dbg.success(f"{len(result.prompts)} prompts")
        return result.prompts

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None,
    ) -> types.GetPromptResult:
        with MCPDebugLogger("prompts/get", f"{name} {_format_args(arguments)}") as dbg:
            start = time.monotonic()
            result = await self.session.get_prompt(name, arguments)
            self._last_duration_ms = (time.monotonic() - start) * 1000
            dbg.success(f"ok ({len(result.messages)} messages)")
        return result

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> types.CallToolResult:
        with MCPDebugLogger("tools/call", f"{name} {_format_args(arguments)}") as dbg:
            start = time.monotonic()
            result = await self.session.call_tool(name, arguments)
            self._last_duration_ms = (time.monotonic() - start) * 1000
            content_count = len(result.content) if result.content else 0
            status = "error" if getattr(result, "isError", False) else "ok"
            dbg.success(f"{status} ({content_count} content items)")
        return result

    async def ping(self) -> bool:
        with MCPDebugLogger("ping") as dbg:
            start = time.monotonic()
            try:
                await self.session.send_ping()
                self._last_duration_ms = (time.monotonic() - start) * 1000
                dbg.success("pong")
                return True
            except Exception:
                self._last_duration_ms = (time.monotonic() - start) * 1000
                return False

    async def close(self) -> None:
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
            self._exit_stack = None
        self._session = None
