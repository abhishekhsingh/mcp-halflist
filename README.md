# mcp-halflist

**Lint your MCP server before your users do.**

CI-first conformance testing CLI for [Model Context Protocol](https://modelcontextprotocol.io) servers. Point it at your server, get a scored health report.

## Installation

```bash
pip install mcp-halflist
```

## Quick Start

```bash
# Full audit of the official MCP reference server
halflist audit --stdio "npx -y @modelcontextprotocol/server-everything"

# JSON output for CI pipelines
halflist audit --stdio "npx -y @modelcontextprotocol/server-everything" --format json
```

### Test your own server

```bash
halflist audit --stdio "python3 my_server.py"
halflist check --stdio "python3 my_server.py" --format json
```

### More examples

```bash
# Time server
halflist check --stdio "npx -y @modelcontextprotocol/server-time"

# Fetch server
halflist check --stdio "npx -y @modelcontextprotocol/server-fetch"

# Filesystem server
halflist check --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
```

## Commands

### `halflist audit` — Full Audit (Recommended)

Run conformance checks + benchmark every tool in a single shot.

```bash
# One command, full picture
halflist audit --stdio "npx -y @modelcontextprotocol/server-everything"

# JSON output for CI
halflist audit --stdio "python3 my_server.py" --format json

# Control benchmark iterations
halflist audit --stdio "python3 my_server.py" --iterations 50
```

### `halflist check` — Conformance Testing

Run protocol conformance checks against an MCP server.

```bash
halflist check --stdio "npx -y @modelcontextprotocol/server-everything"
halflist check --stdio "python3 my_server.py" --format json
halflist check --stdio "python3 my_server.py" --suite handshake --verbose
```

### `halflist bench` — Latency Benchmarking

Benchmark latency per tool with p50/p95/p99 percentiles.

```bash
# Benchmark first 5 tools (default)
halflist bench --stdio "npx -y @modelcontextprotocol/server-everything"

# Benchmark specific tools
halflist bench --stdio "python3 my_server.py" --tool search --tool get_topic

# Benchmark all tools with 50 iterations
halflist bench --stdio "python3 my_server.py" --all --iterations 50

# JSON output
halflist bench --stdio "python3 my_server.py" --format json
```

### `halflist watch` — Health Monitoring

Continuously monitor an MCP server's health.

```bash
# Probe every 60 seconds (default)
halflist watch --stdio "npx -y @modelcontextprotocol/server-time"

# Custom interval, log to file
halflist watch --stdio "python3 my_server.py" --interval 30 --log health.jsonl

# Run 10 probes and exit
halflist watch --stdio "python3 my_server.py" --count 10
```

### `halflist report` — Markdown & Badges

Generate markdown or SVG badge from a halflist JSON report.

```bash
# Generate markdown from audit results
halflist audit --stdio "python3 my_server.py" --format json > results.json
halflist report results.json

# Generate SVG badge
halflist report results.json --badge -o badge.svg

# Generate markdown from bench results
halflist bench --stdio "python3 my_server.py" --format json > bench.json
halflist report bench.json -o BENCH.md
```

## What It Checks

### Handshake Suite
- Server responds to `initialize` with valid response
- Protocol version returned
- Capabilities object present
- Server info has name and version
- `notifications/initialized` accepted
- Ping returns pong

### Tools Suite
- `tools/list` returns valid array
- At least 1 tool exists
- Every tool has a non-empty name
- Every tool has a description
- `inputSchema` contains `"type": "object"`
- No duplicate tool names
- Tool names follow recommended pattern
- Tool call with generated args returns valid response
- Tool call with empty args handles gracefully
- Response content is a list
- Each content item has a type field

## Output Formats

### Terminal (default)

Rich, colored output with a scored summary:

```
╭─ mcp-halflist v0.2.0 ──────────────────────────────────────╮
│                                                              │
│  Server:     my-server v1.0.0                               │
│  Transport:  stdio                                           │
│  Score:      94/100  ████████████████████░░  94%             │
│                                                              │
╰──────────────────────────────────────────────────────────────╯
```

### JSON (`--format json`)

Full structured report suitable for CI integration. Returns a `HalflistReport`, `BenchReport`, or `AuditReport` object with score, suites, benchmarks, and timing data.

### Markdown (`halflist report`)

Generate markdown tables from JSON output, suitable for embedding in README or PR comments.

### SVG Badge (`halflist report --badge`)

Shields.io-style SVG badge showing score or benchmark summary.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed (warnings OK) |
| 1 | One or more failures |
| 2 | Connection/transport error |
| 3 | Configuration error (bad flags) |

## CLI Options

```
halflist audit --stdio <command>   Launch server via stdio (check + bench all tools)
               -n / --iterations   Benchmark iterations per tool (default: 10)
               -w / --warmup       Warmup iterations (default: 2)
               --verbose           Show all check details
               --format <fmt>      Output format: terminal or json
               --quiet / -q        Suppress server stderr
               --timeout <secs>    Timeout per operation (default: 30)

halflist check --stdio <command>   Launch server via stdio
               --format <fmt>      Output format: terminal (default) or json
               --suite <name>      Filter to specific suite(s), repeatable
               --verbose           Show all check details
               --quiet / -q        Suppress server stderr
               --timeout <secs>    Timeout per operation (default: 30)

halflist bench --stdio <command>   Launch server via stdio
               --tool <name>       Benchmark specific tool(s), repeatable
               --all               Benchmark all tools (default: first 5)
               -n / --iterations   Iterations per tool (default: 10)
               -w / --warmup       Warmup iterations (default: 2)
               --format <fmt>      Output format: terminal or json
               --quiet / -q        Suppress server stderr
               --timeout <secs>    Timeout per operation (default: 30)

halflist watch --stdio <command>   Launch server via stdio
               -i / --interval     Seconds between probes (default: 60)
               -c / --count        Number of probes (default: infinite)
               -l / --log <file>   Append JSONL probes to file
               --quiet / -q        Suppress server stderr
               --timeout <secs>    Timeout per operation (default: 30)

halflist report <file.json>        Path to halflist JSON report
               --format <fmt>      Output format: markdown (default)
               --badge             Generate SVG badge instead
               -o / --output       Write to file

halflist --version                 Print version and exit
```

## How It Compares

| | mcp-halflist | MCP Inspector | mcp-probe |
|---|---|---|---|
| **Approach** | Automated test suite | Interactive GUI | Request-level testing |
| **CI-first** | Yes | No | Partial |
| **Scored reports** | Yes | No | No |
| **Benchmarking** | Yes | No | No |
| **Zero config** | Yes | Yes | Yes |

Think of it this way: MCP Inspector and mcp-probe are Postman. mcp-halflist is pytest.

## Development

```bash
git clone https://github.com/abhishekhsingh/mcp-halflist.git
cd mcp-halflist
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run against fixture servers
halflist check --stdio "python tests/servers/good_server.py"
halflist check --stdio "python tests/servers/bad_server.py"

# Lint
ruff check src/ tests/
```

## License

MIT

## Author

[Abhishekh Singh](https://abhishekhsingh.github.io/)
