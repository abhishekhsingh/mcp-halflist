# mcp-halflist

**Lint your MCP server before your users do.**

CI-first conformance testing CLI for [Model Context Protocol](https://modelcontextprotocol.io) servers. Point it at your server, get a scored health report.

## Installation

```bash
pip install mcp-halflist
```

## Quick Start

```bash
# Check a server launched via stdio
halflist check --stdio "python3 my_server.py"

# JSON output for CI pipelines
halflist check --stdio "python3 my_server.py" --format json

# Run only specific suites
halflist check --stdio "python3 my_server.py" --suite handshake --suite tools
```

> **macOS note:** Use `python3` instead of `python` — macOS does not ship `python` on `PATH` by default.

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
╭─ mcp-halflist v0.1.0 ──────────────────────────────────────╮
│                                                              │
│  Server:     my-server v1.0.0                               │
│  Transport:  stdio                                           │
│  Score:      94/100  ████████████████████░░  94%             │
│                                                              │
╰──────────────────────────────────────────────────────────────╯
```

### JSON (`--format json`)

Full structured report suitable for CI integration. Returns a `HalflistReport` object with score, suites, individual check results, and timing data.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed (warnings OK) |
| 1 | One or more failures |
| 2 | Connection/transport error |
| 3 | Configuration error (bad flags) |

## CLI Options

```
halflist check --stdio <command>   Launch server via stdio
               --format <fmt>      Output format: terminal (default) or json
               --suite <name>      Filter to specific suite(s), repeatable
               --verbose           Show all check details
               --timeout <secs>    Timeout per operation (default: 30)
               --version           Print version and exit
```

## How It Compares

| | mcp-halflist | MCP Inspector | mcp-probe |
|---|---|---|---|
| **Approach** | Automated test suite | Interactive GUI | Request-level testing |
| **CI-first** | Yes | No | Partial |
| **Scored reports** | Yes | No | No |
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

## Roadmap

- **v0.2.0** — HTTP/SSE transport, auth support
- **v0.3.0** — `halflist bench` for performance benchmarking
- **v1.0.0** — `halflist watch` for dev mode, full CI integration, JUnit/Markdown output

## License

MIT

## Author

Abhishekh Singh
