# Command Reference

Complete documentation for all halflist commands.

## Exit Codes

All commands that connect to a server use the same exit codes:

| Code | Meaning |
|------|---------|
| 0 | All checks passed (warnings are OK) |
| 1 | One or more checks failed |
| 2 | Connection or transport error |
| 3 | Configuration error (invalid flags, bad file, etc.) |

---

## `halflist check`

Run protocol conformance and security checks against an MCP server.

### Suites

- **handshake** (6 checks) — initialize, protocol version, capabilities, server info, initialized notification, ping/pong
- **tools** (11 checks) — tools/list validation, naming, descriptions, schemas, tool call smoke test
- **resources** (8 checks) — resources/list validation, uri/name checks, resources/read smoke test, content item validation, mimeType format. Skipped if the server does not advertise the resources capability.
- **prompts** (7 checks) — prompts/list validation, name/description checks, prompts/get smoke test, message role/content validation. Skipped if the server does not advertise the prompts capability.
- **security** (5 checks) — prompt injection scan, data exfiltration references, cross-tool manipulation, suspicious encoding, tool pin verification

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--stdio` | | | Command to launch the MCP server via stdio |
| `--http` | | | URL of the MCP server via HTTP (Streamable HTTP with SSE fallback) |
| `--header` | | | HTTP header (`Key: Value`). Repeatable. Requires `--http` |
| `--oauth-token-url` | | | OAuth2 token endpoint URL. Requires `--http` |
| `--oauth-client-id` | | | OAuth2 client ID |
| `--oauth-client-secret` | | | OAuth2 client secret |
| `--oauth-scope` | | | OAuth2 scope (optional) |
| `--format` | | `terminal` | Output format: `terminal` or `json` |
| `--suite` | | all suites | Suite(s) to run. Repeatable (e.g. `--suite handshake --suite security`) |
| `--verbose` | `-v` | off | Show all check details including passing checks |
| `--quiet` | `-q` | off | Suppress server stderr output. Auto-enabled with `--format json` |
| `--timeout` | | `30` | Timeout in seconds per operation |
| `--verify-pins` | | off | Verify tool definitions against a saved pin snapshot |

Either `--stdio` or `--http` is required. They are mutually exclusive. Auth flags (`--header`, `--oauth-*`) require `--http`.

### Examples

```bash
# Basic conformance check (stdio)
halflist check --stdio "npx -y @modelcontextprotocol/server-everything"

# HTTP transport
halflist check --http http://localhost:8080/mcp

# HTTP with bearer token
halflist check --http https://mcp.example.com/v1 --header "Authorization: Bearer tok123"

# HTTP with OAuth2 client credentials
halflist check --http https://mcp.example.com/v1 \
  --oauth-token-url https://auth.example.com/token \
  --oauth-client-id my-client \
  --oauth-client-secret my-secret

# Run only the security suite
halflist check --stdio "python3 my_server.py" --suite security

# Run handshake + tools suites only
halflist check --stdio "python3 my_server.py" --suite handshake --suite tools

# JSON output for CI pipelines
halflist check --stdio "python3 my_server.py" --format json

# Verbose output showing all checks
halflist check --stdio "python3 my_server.py" --verbose

# Quiet mode — suppress server stderr noise
halflist check --stdio "python3 my_server.py" --quiet

# Verify tool definitions against a saved pin
halflist check --stdio "python3 my_server.py" --verify-pins
```

### Score

The score is computed from all checks: PASS = 1.0, WARN = 0.5, SKIP = 0.5, FAIL = 0.0, normalized to 0-100.

When `--suite` is used to filter, the score is **suppressed** in terminal output because a partial run doesn't represent the full server health. The verdict (PASS/FAIL) is still shown. JSON output always includes the computed score.

---

## `halflist bench`

Benchmark latency per tool on an MCP server.

By default, benchmarks the first 5 tools discovered. Use `--all` for every tool, or `--tool` to pick specific ones.

Each tool is called with synthetically generated arguments based on its `inputSchema`. Before measuring, warmup iterations are run and discarded. Tools where all warmup calls fail are reported as **skipped (args rejected)** instead of showing misleading latency data.

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--stdio` | | | Command to launch the MCP server via stdio |
| `--http` | | | URL of the MCP server via HTTP |
| `--header` | | | HTTP header (`Key: Value`). Repeatable. Requires `--http` |
| `--oauth-token-url` | | | OAuth2 token endpoint URL. Requires `--http` |
| `--oauth-client-id` | | | OAuth2 client ID |
| `--oauth-client-secret` | | | OAuth2 client secret |
| `--oauth-scope` | | | OAuth2 scope (optional) |
| `--tool` | | first 5 | Tool(s) to benchmark. Repeatable (e.g. `--tool echo --tool search`) |
| `--all` | | off | Benchmark all discovered tools |
| `--iterations` | `-n` | `10` | Number of measured iterations per tool |
| `--warmup` | `-w` | `2` | Warmup iterations, discarded before measuring |
| `--format` | | `terminal` | Output format: `terminal` or `json` |
| `--quiet` | `-q` | off | Suppress server stderr output. Auto-enabled with `--format json` |
| `--timeout` | | `30` | Timeout in seconds per operation |

Either `--stdio` or `--http` is required. They are mutually exclusive.

### Examples

```bash
# Benchmark first 5 tools (default)
halflist bench --stdio "npx -y @modelcontextprotocol/server-everything"

# Benchmark via HTTP
halflist bench --http http://localhost:8080/mcp --all

# Benchmark all tools
halflist bench --stdio "python3 my_server.py" --all

# Benchmark specific tools
halflist bench --stdio "python3 my_server.py" --tool echo --tool search

# 50 iterations with 5 warmup calls
halflist bench --stdio "python3 my_server.py" --all -n 50 -w 5

# JSON output for CI
halflist bench --stdio "python3 my_server.py" --format json
```

### Output

The terminal table shows p50, p95, p99, min, and max latency per tool, with a colored status dot: green (fast, p99 < 100ms), yellow (moderate, p99 100–1000ms), red (slow, p99 > 1000ms). Sub-millisecond values display as `<1ms`.

Skipped tools appear in dim text:

```
simulate-research-query    skipped (args rejected)
```

The summary line shows benchmarked and skipped counts:

```
5 benchmarked · 2 skipped (args rejected) · 12.4s
```

---

## `halflist audit`

Run all conformance suites + benchmark every tool in a single connection. This is the recommended command for a complete server assessment.

Audit always runs all suites (no `--suite` filter) and benchmarks all discovered tools.

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--stdio` | | | Command to launch the MCP server via stdio |
| `--http` | | | URL of the MCP server via HTTP |
| `--header` | | | HTTP header (`Key: Value`). Repeatable. Requires `--http` |
| `--oauth-token-url` | | | OAuth2 token endpoint URL. Requires `--http` |
| `--oauth-client-id` | | | OAuth2 client ID |
| `--oauth-client-secret` | | | OAuth2 client secret |
| `--oauth-scope` | | | OAuth2 scope (optional) |
| `--iterations` | `-n` | `10` | Benchmark iterations per tool |
| `--warmup` | `-w` | `2` | Warmup iterations, discarded before measuring |
| `--verbose` | `-v` | off | Show all check details including passing checks |
| `--format` | | `terminal` | Output format: `terminal` or `json` |
| `--quiet` | `-q` | off | Suppress server stderr output. Auto-enabled with `--format json` |
| `--timeout` | | `30` | Timeout in seconds per operation |
| `--verify-pins` | | off | Verify tool definitions against a saved pin snapshot |

Either `--stdio` or `--http` is required. They are mutually exclusive.

### Examples

```bash
# Full audit — conformance + security + benchmarks
halflist audit --stdio "npx -y @modelcontextprotocol/server-everything"

# Audit via HTTP
halflist audit --http http://localhost:8080/mcp

# JSON output for CI
halflist audit --stdio "python3 my_server.py" --format json

# With pin verification
halflist audit --stdio "python3 my_server.py" --verify-pins

# More iterations for stable latency numbers
halflist audit --stdio "python3 my_server.py" -n 50 -w 5
```

---

## `halflist watch`

Continuously monitor an MCP server's health. Each probe opens a fresh connection, runs the handshake suite, and reports status.

### Probe Status

| Status | Meaning |
|--------|---------|
| `ok` | Server connected, all handshake checks passed |
| `degraded` | Server connected, but some handshake checks warned or failed |
| `down` | Server failed to connect or crashed during probing |

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--stdio` | | | Command to launch the MCP server via stdio |
| `--http` | | | URL of the MCP server via HTTP |
| `--header` | | | HTTP header (`Key: Value`). Repeatable. Requires `--http` |
| `--oauth-token-url` | | | OAuth2 token endpoint URL. Requires `--http` |
| `--oauth-client-id` | | | OAuth2 client ID |
| `--oauth-client-secret` | | | OAuth2 client secret |
| `--oauth-scope` | | | OAuth2 scope (optional) |
| `--interval` | `-i` | `60` | Seconds between probes |
| `--count` | `-c` | infinite | Number of probes before exiting |
| `--log` | `-l` | none | Append JSONL probe results to this file |
| `--quiet` | `-q` | off | Suppress server stderr output |
| `--timeout` | | `30` | Timeout in seconds per operation |

Either `--stdio` or `--http` is required. They are mutually exclusive.

### Examples

```bash
# Probe every 60 seconds (default), run forever
halflist watch --stdio "npx -y @modelcontextprotocol/server-time"

# Watch an HTTP server
halflist watch --http http://localhost:8080/mcp --interval 30

# Probe every 30 seconds, log to file
halflist watch --stdio "python3 my_server.py" --interval 30 --log health.jsonl

# Run 10 probes and exit
halflist watch --stdio "python3 my_server.py" --count 10

# Quick smoke test — single probe
halflist watch --stdio "python3 my_server.py" --count 1
```

Press `Ctrl+C` to exit cleanly.

---

## `halflist report`

Generate markdown, HTML, or an SVG badge from a halflist JSON report file. Auto-detects whether the JSON is from `check`, `bench`, or `audit`.

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `JSON_FILE` | | *(required)* | Path to a halflist JSON report file |
| `--format` | | `markdown` | Output format: `markdown` or `html` |
| `--badge` | | off | Generate an SVG badge instead of a report |
| `--output` | `-o` | stdout | Write output to a file |

### Examples

```bash
# Generate markdown report
halflist check --stdio "python3 my_server.py" --format json > results.json
halflist report results.json

# Generate HTML report
halflist report results.json --format html -o report.html

# Generate SVG badge
halflist report results.json --badge -o badge.svg

# Pipe directly
halflist audit --stdio "python3 my_server.py" --format json | halflist report /dev/stdin -o audit.md

# Benchmark report as HTML
halflist bench --stdio "python3 my_server.py" --format json > bench.json
halflist report bench.json --format html -o bench.html
```

### HTML Reports

HTML reports are self-contained single files with no external dependencies. They include:
- Dark theme with inline CSS
- SVG donut gauge for score (check and audit reports)
- Collapsible suite sections with per-check details
- Horizontal bar charts for benchmark latency
- Responsive layout

---

## `halflist pin`

Snapshot the current tool definitions (name, description, inputSchema) as SHA-256 hashes. Used with `--verify-pins` on `check` or `audit` to detect tool drift or rug pull attacks.

Pins are stored in `~/.halflist/pins/<server-name>.json` by default.

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--stdio` | | | Command to launch the MCP server via stdio |
| `--http` | | | URL of the MCP server via HTTP |
| `--header` | | | HTTP header (`Key: Value`). Repeatable. Requires `--http` |
| `--oauth-token-url` | | | OAuth2 token endpoint URL. Requires `--http` |
| `--oauth-client-id` | | | OAuth2 client ID |
| `--oauth-client-secret` | | | OAuth2 client secret |
| `--oauth-scope` | | | OAuth2 scope (optional) |
| `--output` | `-o` | `~/.halflist/pins/<name>.json` | Write pin file to a custom path |
| `--quiet` | `-q` | off | Suppress server stderr output |
| `--timeout` | | `30` | Timeout in seconds per operation |

Either `--stdio` or `--http` is required. They are mutually exclusive.

### Examples

```bash
# Pin current tool definitions
halflist pin --stdio "npx -y @modelcontextprotocol/server-everything"

# Pin an HTTP server
halflist pin --http http://localhost:8080/mcp

# Later: check if anything changed
halflist check --stdio "npx -y @modelcontextprotocol/server-everything" --verify-pins

# Pin to a custom path
halflist pin --stdio "python3 my_server.py" -o ./pins/my-server.json
```

### Pin Verification Results

| Result | Meaning |
|--------|---------|
| PASS | All tool hashes match the saved snapshot |
| WARN | New tools added or old tools removed (but no existing tools changed) |
| FAIL | One or more existing tools have changed their definition |
| SKIP | Pin verification was not requested (`--verify-pins` not set) |

### Workflow

```bash
# 1. Pin your server's tools after verifying they're safe
halflist pin --stdio "python3 my_server.py"

# 2. Run checks regularly with pin verification
halflist check --stdio "python3 my_server.py" --verify-pins

# 3. If tools change legitimately, re-pin
halflist pin --stdio "python3 my_server.py"
```
