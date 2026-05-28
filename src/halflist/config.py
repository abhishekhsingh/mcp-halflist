from __future__ import annotations

import os
import re
import stat
import sys
import warnings
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, model_validator

from halflist.constants import EXIT_CONFIG_ERROR

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class ConfigError(Exception):
    pass


# ── Pydantic models ─────────────────────────────────────────────────────────


class OAuthConfig(BaseModel):
    token_url: str | None = None
    client_id: str | None = None
    client_secret: SecretStr | None = None
    scope: str | None = None


class PKCEConfig(BaseModel):
    no_browser: bool = False
    callback_port: int | None = Field(None, gt=0)
    no_auth: bool = False


class ServerConfig(BaseModel):
    transport: str | None = None
    command: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    oauth: OAuthConfig = OAuthConfig()
    pkce: PKCEConfig = PKCEConfig()

    @model_validator(mode="after")
    def validate_transport(self) -> ServerConfig:
        if self.transport is not None and self.transport not in ("stdio", "http"):
            raise ValueError(f"server.transport must be 'stdio' or 'http', got '{self.transport}'")
        if self.transport == "stdio" and not self.command:
            raise ValueError("server.transport = 'stdio' requires server.command to be set")
        if self.transport == "http" and not self.url:
            raise ValueError("server.transport = 'http' requires server.url to be set")
        return self


class CheckConfig(BaseModel):
    suites: list[str] | None = None
    timeout: int | None = Field(None, gt=0)
    verbose: bool = False
    verify_pins: bool = False
    args_file: str | None = None


class BenchConfig(BaseModel):
    iterations: int | None = Field(None, gt=0)
    warmup: int | None = Field(None, gt=0)
    tools: list[str] | None = None
    all: bool = False
    timeout: int | None = Field(None, gt=0)
    args_file: str | None = None


class AuditConfig(BaseModel):
    timeout: int | None = Field(None, gt=0)
    verify_pins: bool = False
    args_file: str | None = None


class WatchConfig(BaseModel):
    interval: int | None = Field(None, gt=0)
    count: int | None = Field(None, gt=0)
    log: str | None = None
    timeout: int | None = Field(None, gt=0)


class OutputConfig(BaseModel):
    format: Literal["terminal", "json"] | None = None
    quiet: bool = False


class PinConfig(BaseModel):
    timeout: int | None = Field(None, gt=0)


class ReportConfig(BaseModel):
    format: Literal["markdown", "html"] | None = None


class DebugConfig(BaseModel):
    enabled: bool = False
    log_file: str | None = None


class HalflistConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    check: CheckConfig = CheckConfig()
    bench: BenchConfig = BenchConfig()
    audit: AuditConfig = AuditConfig()
    watch: WatchConfig = WatchConfig()
    pin: PinConfig = PinConfig()
    report: ReportConfig = ReportConfig()
    output: OutputConfig = OutputConfig()
    debug: DebugConfig = DebugConfig()


# ── Env var expansion ────────────────────────────────────────────────────────

_ENV_PATTERN = re.compile(r"\$\{([^}]+)}")


def _expand_env_vars(value: str, key_path: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            raise ConfigError(
                f"Environment variable ${{{var_name}}} is not set (referenced by '{key_path}')"
            )
        return env_value

    return _ENV_PATTERN.sub(replacer, value)


def _expand_recursive(obj: Any, path: str = "") -> Any:
    if isinstance(obj, str):
        return _expand_env_vars(obj, path)
    if isinstance(obj, dict):
        return {k: _expand_recursive(v, f"{path}.{k}" if path else k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_recursive(v, f"{path}[{i}]") for i, v in enumerate(obj)]
    return obj


# ── Known keys (for unknown-key warnings) ───────────────────────────────────

_KNOWN_KEYS: dict[str, set[str] | dict[str, set[str]]] = {
    "server": {
        "_self": {"transport", "command", "url", "headers"},
        "oauth": {"token_url", "client_id", "client_secret", "scope"},
        "pkce": {"no_browser", "callback_port", "no_auth"},
    },
    "check": {"suites", "timeout", "verbose", "verify_pins", "args_file"},
    "bench": {"iterations", "warmup", "tools", "all", "timeout", "args_file"},
    "audit": {"timeout", "verify_pins", "args_file"},
    "watch": {"interval", "count", "log", "timeout"},
    "pin": {"timeout"},
    "report": {"format"},
    "output": {"format", "quiet"},
    "debug": {"enabled", "log_file"},
}


def _warn_unknown_keys(data: dict[str, Any]) -> None:
    for section, value in data.items():
        if section not in _KNOWN_KEYS:
            warnings.warn(f"halflist.toml: unknown section [{section}]", stacklevel=2)
            continue
        if not isinstance(value, dict):
            continue
        known = _KNOWN_KEYS[section]
        if isinstance(known, dict):
            allowed_top = known.get("_self", set())
            sub_sections = {k for k in known if k != "_self"}
            for key in value:
                if key in sub_sections:
                    if isinstance(value[key], dict):
                        sub_known = known[key]
                        if not isinstance(sub_known, set):
                            continue
                        for sub_key in value[key]:
                            if sub_key not in sub_known:
                                warnings.warn(
                                    f"halflist.toml: unknown key '{sub_key}' in [{section}.{key}]",
                                    stacklevel=2,
                                )
                elif key not in allowed_top:
                    warnings.warn(
                        f"halflist.toml: unknown key '{key}' in [{section}]", stacklevel=2
                    )
        else:
            for key in value:
                if key not in known:
                    warnings.warn(
                        f"halflist.toml: unknown key '{key}' in [{section}]", stacklevel=2
                    )


# ── Loader ───────────────────────────────────────────────────────────────────

_SEARCH_PATHS = [
    Path("halflist.toml"),
    Path(".halflist.toml"),
    Path.home() / ".halflist" / "config.toml",
]


def _find_config(config_path: str | None) -> Path | None:
    if config_path is not None:
        p = Path(config_path)
        if not p.exists():
            raise ConfigError(f"Config file not found: {config_path}")
        return p

    for candidate in _SEARCH_PATHS:
        if candidate.exists():
            return candidate
    return None


def _warn_file_permissions(path: Path, data: dict[str, Any]) -> None:
    oauth = data.get("server", {}).get("oauth", {})
    if not oauth.get("client_secret"):
        return
    try:
        mode = path.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            warnings.warn(
                f"halflist.toml: {path} contains secrets but is readable by group/others "
                f"(mode {oct(mode & 0o777)}). Consider: chmod 600 {path}",
                stacklevel=2,
            )
    except OSError:
        pass


def load_config(config_path: str | None = None) -> HalflistConfig | None:
    try:
        path = _find_config(config_path)
    except ConfigError as e:
        _config_exit(str(e))
        return None  # unreachable

    if path is None:
        return None

    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode())
    except Exception as e:
        _config_exit(f"Failed to parse {path}: {e}")
        return None

    _warn_unknown_keys(data)
    _warn_file_permissions(path, data)

    try:
        data = _expand_recursive(data)
    except ConfigError as e:
        _config_exit(str(e))
        return None

    try:
        return HalflistConfig.model_validate(data)
    except Exception as e:
        _config_exit(f"Invalid config in {path}: {e}")
        return None


def _config_exit(message: str) -> None:
    import typer

    from rich.console import Console

    Console(stderr=True).print(f"[red]Error:[/red] {message}")
    raise typer.Exit(EXIT_CONFIG_ERROR)


# ── Merge helpers ────────────────────────────────────────────────────────────


def merge_str(cli: str | None, config_val: str | None, default: str) -> str:
    if cli is not None:
        return cli
    if config_val is not None:
        return config_val
    return default


def merge_int(cli: int | None, config_val: int | None, default: int) -> int:
    if cli is not None:
        return cli
    if config_val is not None:
        return config_val
    return default


def merge_bool(cli: bool, config_val: bool) -> bool:
    return cli or config_val


def merge_optional_str(cli: str | None, config_val: str | None) -> str | None:
    if cli is not None:
        return cli
    return config_val


def merge_headers(
    cli_headers: list[str] | None,
    config_headers: dict[str, str] | None,
) -> list[str] | None:
    if not config_headers:
        return cli_headers
    # Config headers first, CLI appended after so later entries win in _resolve_headers
    result = [f"{k}: {v}" for k, v in config_headers.items()]
    if cli_headers:
        result.extend(cli_headers)
    return result
