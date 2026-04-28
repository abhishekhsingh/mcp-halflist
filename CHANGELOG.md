# Changelog

## 0.2.0 (2026-04-28)

### Added
- `halflist audit` — full conformance check + benchmark in one shot
  - Runs all suites + benchmarks all tools with a single connection
  - Combined `AuditReport` JSON with both suites and benchmarks
  - `halflist report` auto-detects audit JSON for markdown generation
- `halflist bench` — latency benchmarking per tool with p50/p95/p99 percentiles
  - `--tool` filter (repeatable), `--all`, `--iterations/-n`, `--warmup/-w`
  - Rich terminal output with live progress and results table
  - JSON output (`--format json`)
- `halflist watch` — continuous health monitoring with JSONL output
  - `--interval/-i`, `--count/-c`, `--log/-l` for file logging
  - Per-probe status: ok / degraded / down
- `halflist report` — generate markdown or SVG badge from JSON output
  - `--badge` for shields.io-style SVG
  - `--format markdown` (default)
  - `-o` to write to file
- Schema-based dummy argument generation reused for bench tool calls
- Differentiated empty vs absent tool description warnings in tools suite

### Changed
- `--quiet` / `-q` flag now suppresses server stderr (auto-enabled with `--format json`)

## 0.1.0 (2026-04-28)

Initial release.

- `halflist check` command with stdio transport
- Handshake suite (6 checks)
- Tools suite (11 checks)
- Terminal output with Rich formatting
- JSON output (`--format json`)
- Schema-based dummy argument generation for tool smoke tests
- Suite filtering (`--suite`)
- CI-friendly exit codes (0 = pass, 1 = fail, 2 = transport error, 3 = config error)
