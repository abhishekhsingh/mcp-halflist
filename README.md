# mcp-halflist

CI-first conformance, security, and benchmarking CLI for MCP servers.

**Lint your MCP server before your users do.**

![PyPI](https://img.shields.io/pypi/v/mcp-halflist)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/pypi/pyversions/mcp-halflist)

## What It Does

Point it at any [MCP](https://modelcontextprotocol.io) server and get a scored conformance report, security vulnerability scan (prompt injection, tool poisoning, data exfiltration), and per-tool latency benchmarks. Fully offline, zero API keys, CI-native. One `pip install`, one command, done.

## See It In Action

**Terminal output:**

![halflist audit output](https://github.com/abhishekhsingh/mcp-halflist/blob/main/examples/terminal-output.png?raw=true)

**HTML report:** [View example report](https://github.com/abhishekhsingh/mcp-halflist/blob/main/examples/audit-report.html)

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

halflist scans tool descriptions for prompt injection, data exfiltration instructions, cross-tool manipulation, suspicious encoding (base64, zero-width characters), and rug pull attempts via tool pinning. All scanning is fully offline — zero API calls, zero data sharing. Unlike [mcp-scan](https://github.com/invariantlabs-ai/mcp-scan) which sends tool descriptions to an external API, halflist runs entirely on your machine.

See [security scanning details](https://github.com/abhishekhsingh/mcp-halflist/blob/main/docs/security.md) for the full list of detection patterns.

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

## License

MIT

## Author

[Abhishekh Singh](https://abhishekhsingh.github.io/)
