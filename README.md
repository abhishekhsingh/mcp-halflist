# mcp-halflist

CI-first conformance, security, and benchmarking CLI for MCP servers.

**Lint your MCP server before your users do.**

[![CI](https://github.com/abhishekhsingh/mcp-halflist/actions/workflows/ci.yml/badge.svg)](https://github.com/abhishekhsingh/mcp-halflist/actions/workflows/ci.yml)
![PyPI](https://img.shields.io/pypi/v/mcp-halflist)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/pypi/pyversions/mcp-halflist)

## What It Does

Point it at any [MCP](https://modelcontextprotocol.io) server (stdio or HTTP) and get a scored conformance report, security vulnerability scan (prompt injection, tool poisoning, data exfiltration), and per-tool latency benchmarks. Fully offline, zero API keys, CI-native. One `pip install`, one command, done.

## See It In Action

**Terminal output:**

![halflist audit output](https://github.com/abhishekhsingh/mcp-halflist/blob/main/examples/terminal-output.png?raw=true)

**HTML reports:**
[Check report](https://github.com/abhishekhsingh/mcp-halflist/blob/main/examples/check-report.html) ·
[Bench report](https://github.com/abhishekhsingh/mcp-halflist/blob/main/examples/bench-report.html) ·
[Audit report](https://github.com/abhishekhsingh/mcp-halflist/blob/main/examples/audit-report.html)

## Install

```bash
pip install mcp-halflist
```

> macOS users: use `python3` instead of `python` in server commands.

## Quick Start

```bash
# Full audit of the official MCP reference server (runs instantly, no setup)
halflist audit --stdio "npx -y @modelcontextprotocol/server-everything"

# Security scan + conformance check
halflist check --stdio "npx -y @modelcontextprotocol/server-everything"

# Benchmark tool latency
halflist bench --stdio "npx -y @modelcontextprotocol/server-everything" --all

# Pin tools, then verify later for rug pull detection
halflist pin --stdio "npx -y @modelcontextprotocol/server-everything"
halflist check --stdio "npx -y @modelcontextprotocol/server-everything" --verify-pins

# Your own server
halflist audit --stdio "python3 my_server.py"

# HTTP transport (Streamable HTTP with SSE fallback)
halflist check --http http://localhost:8080/mcp
halflist audit --http http://localhost:8080/mcp

# HTTP with auth
halflist check --http https://mcp.example.com/v1 --header "Authorization: Bearer tok123"

# HTTP with OAuth2 client credentials
halflist audit --http https://mcp.example.com/v1 \
  --oauth-token-url https://auth.example.com/token \
  --oauth-client-id my-client \
  --oauth-client-secret my-secret

# OAuth2 PKCE (automatic on 401, opens browser for authorization)
halflist check --http https://mcp.example.com/v1

# OAuth2 PKCE headless mode (prints URL instead of opening browser)
halflist check --http https://mcp.example.com/v1 --no-browser

# Skip automatic OAuth PKCE
halflist check --http https://mcp.example.com/v1 --no-auth

# Custom tool arguments for tools that need specific inputs
# args.json: {"get_user": {"user_id": "abc123"}}
halflist bench --http http://localhost:8080/mcp --tool get_user --args-file args.json

# More real servers to try
halflist check --stdio "npx -y @modelcontextprotocol/server-time"
halflist check --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
```

## Commands

| Command | What it does |
|---------|-------------|
| `halflist check` | Protocol conformance + security scanning |
| `halflist bench` | Per-tool latency benchmarking (p50/p95/p99) |
| `halflist audit` | Combined check + bench in one shot |
| `halflist watch` | Continuous health monitoring |
| `halflist report` | Generate markdown, HTML reports, or SVG badges from JSON |
| `halflist pin` | Save tool hashes for rug pull detection |

See the [full command reference](https://github.com/abhishekhsingh/mcp-halflist/blob/main/docs/commands.md) for all flags and examples.

## Security Scanning

halflist scans tool descriptions for prompt injection, data exfiltration instructions, cross-tool manipulation, suspicious encoding (base64, zero-width characters), and rug pull attempts via tool pinning. All scanning runs locally: zero API calls, zero data sharing. Unlike [mcp-scan](https://github.com/invariantlabs-ai/mcp-scan) which sends tool descriptions to an external API, halflist runs entirely on your machine.

See [security scanning details](https://github.com/abhishekhsingh/mcp-halflist/blob/main/docs/security.md) for the full list of detection patterns.

## Debug Logging

```bash
# Enable debug output
halflist check --stdio "python3 server.py" --debug

# Save debug log to file
halflist audit --http https://example.com/mcp --debug-log debug.log

# Environment variable (useful in CI)
HALFLIST_LOG_LEVEL=DEBUG halflist audit --stdio "python3 server.py"
```

## Output Formats

Terminal (colored, default) · JSON (`--format json`) · Markdown · HTML · SVG Badge

See the [output format reference](https://github.com/abhishekhsingh/mcp-halflist/blob/main/docs/output-formats.md) for details.

## How It Compares

| Tool | Approach | Needs API key | Sends data externally |
|------|----------|---------------|----------------------|
| [MCP Inspector](https://github.com/modelcontextprotocol/inspector) | Interactive browser UI | No | No |
| [mcp-probe](https://github.com/nicholasgriffintn/mcp-probe) | Interactive TUI (Rust) | No | No |
| [mcp-server-tester](https://github.com/apify/mcp-server-tester) | LLM-generated tests | Yes (Anthropic) | Yes |
| [mcp-scan](https://github.com/invariantlabs-ai/mcp-scan) | Security scanning | Yes (OpenAI for local) | Yes (Invariant API) |
| **mcp-halflist** | **CI-first check + security + bench** | **No** | **No** |

## Development

```bash
git clone https://github.com/abhishekhsingh/mcp-halflist.git
cd mcp-halflist
pip install -e ".[dev]"
ruff check src/ tests/
ruff format --check src/ tests/
pytest -v --tb=short
```

## License

MIT

## Author

[Abhishekh Singh](https://abhishekhsingh.github.io/)
