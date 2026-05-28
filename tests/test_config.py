from __future__ import annotations

import sys
import textwrap
import warnings
from pathlib import Path

import pytest
from click.exceptions import Exit as ClickExit

from halflist.config import (
    ConfigError,
    HalflistConfig,
    _expand_recursive,
    _warn_file_permissions,
    load_config,
    merge_bool,
    merge_headers,
    merge_int,
    merge_str,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── Config loading ───────────────────────────────────────────────────────────


def test_load_from_explicit_path() -> None:
    config = load_config(str(FIXTURES / "halflist.toml"))
    assert config is not None
    assert config.server.transport == "stdio"
    assert config.server.command == "python3 my_server.py"


def test_load_from_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[server]\ntransport = "http"\nurl = "http://localhost:8080/mcp"\n')
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert config is not None
    assert config.server.url == "http://localhost:8080/mcp"


def test_load_dotfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml = tmp_path / ".halflist.toml"
    toml.write_text("[debug]\nenabled = true\n")
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert config is not None
    assert config.debug.enabled is True


def test_load_global(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    global_dir = tmp_path / ".halflist"
    global_dir.mkdir()
    (global_dir / "config.toml").write_text('[output]\nformat = "json"\n')
    (tmp_path / "subdir").mkdir()
    monkeypatch.chdir(tmp_path / "subdir")
    monkeypatch.setattr(
        "halflist.config._SEARCH_PATHS",
        [
            Path("halflist.toml"),
            Path(".halflist.toml"),
            global_dir / "config.toml",
        ],
    )
    config = load_config()
    assert config is not None
    assert config.output.format == "json"


def test_explicit_path_missing_exits() -> None:
    with pytest.raises(ClickExit):
        load_config("/nonexistent/halflist.toml")


def test_no_config_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "halflist.config._SEARCH_PATHS",
        [
            Path("halflist.toml"),
            Path(".halflist.toml"),
            tmp_path / ".halflist" / "config.toml",
        ],
    )
    config = load_config()
    assert config is None


# ── TOML parsing ─────────────────────────────────────────────────────────────


def test_valid_toml_parses() -> None:
    config = load_config(str(FIXTURES / "halflist.toml"))
    assert config is not None
    assert config.server.transport == "stdio"
    assert config.server.command == "python3 my_server.py"
    assert config.server.oauth.token_url == "https://auth.example.com/token"
    assert config.server.oauth.client_id == "test-client"
    assert config.server.oauth.client_secret is not None
    assert config.server.oauth.client_secret.get_secret_value() == "test-secret"
    assert config.server.pkce.no_browser is True
    assert config.server.pkce.callback_port == 3035
    assert config.check.suites == ["security", "tools"]
    assert config.check.timeout == 45
    assert config.check.verbose is True
    assert config.check.args_file == "check-args.json"
    assert config.bench.iterations == 20
    assert config.bench.warmup == 5
    assert config.bench.tools == ["echo", "add"]
    assert config.bench.timeout == 60
    assert config.bench.args_file == "args.json"
    assert config.audit.timeout == 90
    assert config.audit.verify_pins is True
    assert config.watch.interval == 120
    assert config.watch.count == 10
    assert config.pin.timeout == 30
    assert config.report.format == "html"
    assert config.output.format == "json"
    assert config.output.quiet is True
    assert config.debug.enabled is True
    assert config.debug.log_file == "debug.log"


def test_invalid_toml_exits(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("[server\nbroken")
    with pytest.raises(ClickExit):
        load_config(str(bad))


def test_unknown_keys_warn(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[server]\nfoo = "bar"\n')
    with pytest.warns(UserWarning, match="unknown key 'foo' in \\[server\\]"):
        load_config(str(toml))


def test_partial_config(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[server]\ntransport = "stdio"\ncommand = "echo hi"\n')
    config = load_config(str(toml))
    assert config is not None
    assert config.server.command == "echo hi"
    assert config.bench.iterations is None
    assert config.debug.enabled is False


def test_invalid_transport_exits(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[server]\ntransport = "websocket"\n')
    with pytest.raises(ClickExit):
        load_config(str(toml))


# ── Env var expansion ────────────────────────────────────────────────────────


def test_env_var_expanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HALFLIST_TEST_URL", "http://expanded.example.com")
    toml = tmp_path / "halflist.toml"
    toml.write_text('[server]\ntransport = "http"\nurl = "${HALFLIST_TEST_URL}"\n')
    config = load_config(str(toml))
    assert config is not None
    assert config.server.url == "http://expanded.example.com"


def test_missing_env_var_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NONEXISTENT_VAR_12345", raising=False)
    toml = tmp_path / "halflist.toml"
    toml.write_text('[server]\nurl = "${NONEXISTENT_VAR_12345}"\n')
    with pytest.raises(ClickExit):
        load_config(str(toml))


def test_no_env_vars_unchanged(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[server]\ncommand = "python3 server.py"\n')
    config = load_config(str(toml))
    assert config is not None
    assert config.server.command == "python3 server.py"


def test_env_var_in_headers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "secret123")
    toml = tmp_path / "halflist.toml"
    toml.write_text(
        textwrap.dedent("""\
        [server]
        transport = "http"
        url = "http://example.com"
        [server.headers]
        Authorization = "Bearer ${MY_TOKEN}"
    """)
    )
    config = load_config(str(toml))
    assert config is not None
    assert config.server.headers == {"Authorization": "Bearer secret123"}


def test_env_var_error_includes_key_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_VAR", raising=False)
    data = {"server": {"url": "${MISSING_VAR}"}}
    with pytest.raises(ConfigError, match="MISSING_VAR.*server.url"):
        _expand_recursive(data)


# ── Merge logic ──────────────────────────────────────────────────────────────


def test_merge_str_cli_wins() -> None:
    assert merge_str("cli", "config", "default") == "cli"


def test_merge_str_config_wins() -> None:
    assert merge_str(None, "config", "default") == "config"


def test_merge_str_default() -> None:
    assert merge_str(None, None, "default") == "default"


def test_merge_int_cli_wins() -> None:
    assert merge_int(10, 20, 30) == 10


def test_merge_int_config_wins() -> None:
    assert merge_int(None, 20, 30) == 20


def test_merge_int_default() -> None:
    assert merge_int(None, None, 30) == 30


def test_merge_bool_cli_true_wins() -> None:
    assert merge_bool(True, False) is True


def test_merge_bool_config_true() -> None:
    assert merge_bool(False, True) is True


def test_merge_bool_both_false() -> None:
    assert merge_bool(False, False) is False


def test_merge_headers_no_config() -> None:
    assert merge_headers(["Auth: tok"], None) == ["Auth: tok"]


def test_merge_headers_no_cli() -> None:
    assert merge_headers(None, {"Auth": "tok"}) == ["Auth: tok"]


def test_merge_headers_cli_overrides() -> None:
    result = merge_headers(["Auth: cli-tok"], {"Auth": "config-tok"})
    assert result is not None
    headers = {}
    for h in result:
        k, v = h.split(": ", 1)
        headers[k] = v
    assert headers["Auth"] == "cli-tok"


def test_merge_headers_both_present() -> None:
    result = merge_headers(["X-Custom: val"], {"Auth": "tok"})
    assert result is not None
    assert len(result) == 2


# ── CLI integration ──────────────────────────────────────────────────────────


def test_config_flag_on_all_commands() -> None:
    import re

    from typer.testing import CliRunner

    from halflist.cli import app

    _ansi = re.compile(r"\x1b\[[0-9;]*m")
    runner = CliRunner()
    for cmd in ("check", "bench", "audit", "watch", "pin", "report"):
        result = runner.invoke(app, [cmd, "--help"])
        plain = _ansi.sub("", result.output)
        assert "--config" in plain, f"--config missing from {cmd}"


def test_check_with_config_file(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from halflist.cli import app

    servers = Path(__file__).parent / "servers"
    toml = tmp_path / "halflist.toml"
    toml.write_text(
        textwrap.dedent(f"""\
        [server]
        transport = "stdio"
        command = "{sys.executable} {servers / "good_server.py"}"
    """)
    )
    runner = CliRunner()
    result = runner.invoke(app, ["check", "--config", str(toml)])
    assert result.exit_code == 0


def test_config_server_overridden_by_cli(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from halflist.cli import app

    servers = Path(__file__).parent / "servers"
    toml = tmp_path / "halflist.toml"
    toml.write_text(
        textwrap.dedent("""\
        [server]
        transport = "stdio"
        command = "this-does-not-exist"
    """)
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "check",
            "--config",
            str(toml),
            "--stdio",
            f"{sys.executable} {servers / 'good_server.py'}",
        ],
    )
    assert result.exit_code == 0


def test_config_timeout_used(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from halflist.cli import app

    servers = Path(__file__).parent / "servers"
    toml = tmp_path / "halflist.toml"
    toml.write_text(
        textwrap.dedent(f"""\
        [server]
        transport = "stdio"
        command = "{sys.executable} {servers / "good_server.py"}"

        [check]
        timeout = 60
    """)
    )
    runner = CliRunner()
    result = runner.invoke(app, ["check", "--config", str(toml)])
    assert result.exit_code == 0


def test_no_config_uses_defaults() -> None:
    from typer.testing import CliRunner

    from halflist.cli import app

    servers = Path(__file__).parent / "servers"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["check", "--stdio", f"{sys.executable} {servers / 'good_server.py'}"],
    )
    assert result.exit_code == 0


# ── Empty and edge-case configs ─────────────────────────────────────────────


def test_empty_config_file(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text("")
    config = load_config(str(toml))
    assert config is not None
    assert config.server.transport is None
    assert config.check.timeout is None
    assert config.debug.enabled is False


def test_unknown_section_warns(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[banana]\ncolor = "yellow"\n')
    with pytest.warns(UserWarning, match="unknown section \\[banana\\]"):
        load_config(str(toml))


def test_nested_unknown_key_warns(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[server.oauth]\nbogus = "nope"\n')
    with pytest.warns(UserWarning, match="unknown key 'bogus' in \\[server.oauth\\]"):
        load_config(str(toml))


def test_env_var_in_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUITE_NAME", "security")
    data = {"check": {"suites": ["${SUITE_NAME}", "tools"]}}
    result = _expand_recursive(data)
    assert result == {"check": {"suites": ["security", "tools"]}}


# ── Integer validation ──────────────────────────────────────────────────────


def test_negative_timeout_rejected(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text("[check]\ntimeout = -1\n")
    with pytest.raises(ClickExit):
        load_config(str(toml))


def test_zero_timeout_rejected(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text("[bench]\niterations = 0\n")
    with pytest.raises(ClickExit):
        load_config(str(toml))


def test_negative_interval_rejected(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text("[watch]\ninterval = -5\n")
    with pytest.raises(ClickExit):
        load_config(str(toml))


# ── Format validation ──────────────────────────────────────────────────────


def test_invalid_output_format_rejected(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[output]\nformat = "xml"\n')
    with pytest.raises(ClickExit):
        load_config(str(toml))


def test_invalid_report_format_rejected(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[report]\nformat = "csv"\n')
    with pytest.raises(ClickExit):
        load_config(str(toml))


# ── Transport companion validation ──────────────────────────────────────────


def test_stdio_without_command_rejected(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[server]\ntransport = "stdio"\n')
    with pytest.raises(ClickExit):
        load_config(str(toml))


def test_http_without_url_rejected(tmp_path: Path) -> None:
    toml = tmp_path / "halflist.toml"
    toml.write_text('[server]\ntransport = "http"\n')
    with pytest.raises(ClickExit):
        load_config(str(toml))


# ── SecretStr ───────────────────────────────────────────────────────────────


def test_secret_str_not_in_repr() -> None:
    config = HalflistConfig.model_validate({"server": {"oauth": {"client_secret": "super-secret"}}})
    assert "super-secret" not in repr(config)
    assert config.server.oauth.client_secret is not None
    assert config.server.oauth.client_secret.get_secret_value() == "super-secret"


# ── File permission warnings ───────────────────────────────────────────────


def test_world_readable_config_with_secret_warns(tmp_path: Path) -> None:
    import os
    import stat

    toml = tmp_path / "halflist.toml"
    toml.write_text('[server.oauth]\nclient_secret = "s3cret"\n')
    os.chmod(toml, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    data = {"server": {"oauth": {"client_secret": "s3cret"}}}
    with pytest.warns(UserWarning, match="readable by group/others"):
        _warn_file_permissions(toml, data)


def test_private_config_with_secret_no_warning(tmp_path: Path) -> None:
    import os
    import stat

    toml = tmp_path / "halflist.toml"
    toml.write_text('[server.oauth]\nclient_secret = "s3cret"\n')
    os.chmod(toml, stat.S_IRUSR | stat.S_IWUSR)
    data = {"server": {"oauth": {"client_secret": "s3cret"}}}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _warn_file_permissions(toml, data)


# ── _resolve_server_config ──────────────────────────────────────────────────


def test_resolve_server_config_cli_wins() -> None:
    from halflist.cli import _resolve_server_config

    config = HalflistConfig.model_validate(
        {"server": {"transport": "stdio", "command": "echo config"}}
    )
    stdio, http = _resolve_server_config("echo cli", None, config)
    assert stdio == "echo cli"
    assert http is None


def test_resolve_server_config_infer_from_command() -> None:
    from halflist.cli import _resolve_server_config

    config = HalflistConfig.model_validate({"server": {"command": "echo hi"}})
    stdio, http = _resolve_server_config(None, None, config)
    assert stdio == "echo hi"
    assert http is None


def test_resolve_server_config_infer_from_url() -> None:
    from halflist.cli import _resolve_server_config

    config = HalflistConfig.model_validate({"server": {"url": "http://example.com/mcp"}})
    stdio, http = _resolve_server_config(None, None, config)
    assert stdio is None
    assert http == "http://example.com/mcp"


def test_resolve_server_config_none_without_config() -> None:
    from halflist.cli import _resolve_server_config

    stdio, http = _resolve_server_config(None, None, None)
    assert stdio is None
    assert http is None
