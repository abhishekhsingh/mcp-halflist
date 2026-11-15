"""Headless (--no-browser) login: stdin handling and URL printing."""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
import textwrap
from collections.abc import Iterator

import httpx
import pytest

from halflist.oauth_pkce import CallbackServer, _headless_callback, _print_url_handler


@pytest.fixture
def stdin_pipe(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    """Replace stdin with the read end of a pipe and return the write end."""
    read_fd, write_fd = os.pipe()
    monkeypatch.setattr(sys, "stdin", os.fdopen(read_fd))
    try:
        yield write_fd
    finally:
        try:
            os.close(write_fd)
        except OSError:
            pass


async def _hit(port: int, query: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://127.0.0.1:{port}/callback?{query}")
    assert resp.status_code == 200


async def _login_via_callback(server: CallbackServer) -> tuple[str, str | None]:
    """Start the headless wait, let it settle, then deliver the redirect to the callback server."""
    task = asyncio.ensure_future(_headless_callback(server))
    await asyncio.sleep(0.3)
    assert not task.done(), "the login must keep waiting for the callback"
    await _hit(server.port, "code=cb&state=st")
    return await asyncio.wait_for(task, timeout=5)


# ── stdin that cannot provide input must not abort the login ────────────────


@pytest.mark.asyncio
async def test_empty_stdin_does_not_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    server = CallbackServer()
    try:
        server.start(asyncio.get_running_loop())
        assert await _login_via_callback(server) == ("cb", "st")
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_closed_pipe_stdin_does_not_abort(stdin_pipe: int) -> None:
    os.close(stdin_pipe)  # the writer is gone: stdin is at end of file
    server = CallbackServer()
    try:
        server.start(asyncio.get_running_loop())
        assert await _login_via_callback(server) == ("cb", "st")
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_missing_stdin_does_not_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", None)
    server = CallbackServer()
    try:
        server.start(asyncio.get_running_loop())
        assert await _login_via_callback(server) == ("cb", "st")
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_empty_lines_are_ignored(stdin_pipe: int) -> None:
    os.write(stdin_pipe, b"\n\n   \n")
    server = CallbackServer()
    try:
        server.start(asyncio.get_running_loop())
        assert await _login_via_callback(server) == ("cb", "st")
    finally:
        server.stop()


# ── pasting the callback URL still works ────────────────────────────────────


@pytest.mark.asyncio
async def test_paste_through_pipe(stdin_pipe: int) -> None:
    server = CallbackServer()
    try:
        server.start(asyncio.get_running_loop())
        task = asyncio.ensure_future(_headless_callback(server))
        await asyncio.sleep(0.2)
        pasted = "http://127.0.0.1:3030/callback?code=p1&state=s1&iss=https%3A%2F%2Fauth.example\n"
        os.write(stdin_pipe, pasted.encode())
        assert await asyncio.wait_for(task, timeout=5) == ("p1", "s1")
        assert server.iss == "https://auth.example"
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_paste_after_empty_line(stdin_pipe: int) -> None:
    os.write(stdin_pipe, b"\nhttp://127.0.0.1:3030/callback?code=p2&state=s2\n")
    server = CallbackServer()
    try:
        server.start(asyncio.get_running_loop())
        assert await asyncio.wait_for(_headless_callback(server), timeout=5) == ("p2", "s2")
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_paste_without_trailing_newline_then_eof(stdin_pipe: int) -> None:
    os.write(stdin_pipe, b"http://127.0.0.1:3030/callback?code=p3&state=s3")
    os.close(stdin_pipe)
    server = CallbackServer()
    try:
        server.start(asyncio.get_running_loop())
        assert await asyncio.wait_for(_headless_callback(server), timeout=5) == ("p3", "s3")
    finally:
        server.stop()


# ── the process must exit once the login is done ────────────────────────────


def test_process_exits_when_login_finishes_with_stdin_left_open() -> None:
    """A thread blocked on stdin used to keep the process alive until stdin was closed."""
    script = textwrap.dedent(
        """
        import asyncio, threading, urllib.request
        from halflist.oauth_pkce import CallbackServer, _headless_callback

        async def main():
            server = CallbackServer()
            server.start(asyncio.get_running_loop())
            url = f"http://127.0.0.1:{server.port}/callback?code=c&state=s"
            threading.Timer(0.5, lambda: urllib.request.urlopen(url).read()).start()
            print("RESULT", await _headless_callback(server), flush=True)
            server.stop()

        asyncio.run(main())
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,  # open, and nothing is ever written to it
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Do not use communicate(): it closes stdin, which would hide the problem.
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("process did not exit after the login finished (stdin reader blocked it)")
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.stdin.close()
    out = proc.stdout.read()
    assert "RESULT ('c', 's')" in out
    assert proc.returncode == 0


# ── the authorization URL is printed as one piece ───────────────────────────


@pytest.mark.asyncio
async def test_authorization_url_is_not_folded(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLUMNS", "40")
    url = "http://127.0.0.1:9300/authorize?response_type=code&client_id=cid-1&state=" + "x" * 80
    await _print_url_handler(url)
    assert url in capsys.readouterr().err
