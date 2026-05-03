# Changelog

## 0.4.0 (2026-05-03)

### Features
- **HTTP transport** — `--http` flag with Streamable HTTP → SSE automatic fallback
- **Authentication flags** — `--header`, `--oauth-token-url`, `--oauth-client-id`, `--oauth-client-secret`, `--oauth-scope` on all server-connecting commands
- **Resources suite** (8 checks) — resources/list validation, uri/name checks, resources/read smoke test, content item validation, mimeType format
- **Prompts suite** (7 checks) — prompts/list validation, name/description checks, prompts/get smoke test, message role/content validation

### Visual
- **Terminal aesthetic overhaul** — green-on-black theme, monospace styling, scan line animation in HTML reports
- **HTML report makeover** — terminal-inspired dark theme with CSS custom properties, fixed nav on audit reports, print styles
- **Colored status dots** in bench tables — green (fast), yellow (moderate), red (slow) based on p99 latency
- **HALFLIST logo** in HTML reports — clean letter-spaced text replacing box-drawing ASCII art

### Improvements
- `_build_suite_map()` extracted helper removes duplicated suite registration dicts in cli.py
- `DEFAULT_TIMEOUT` constant used consistently across cli.py, client.py, auth.py
- `Literal["PASS", "FAIL", "WARN", "SKIP"]` for type-safe status values in suite base class
- Security pattern refinements: `.{0,80}` bounded match instead of unbounded `.*`, HTML comment detection moved from FAIL to WARN, `.env` pattern tightened to exclude `.env.example`
- `BaseException` catch on first HTTP transport attempt preserves SSE fallback when MCP SDK leaks CancelledError
- Discovery failure logging for resources and prompts in `_discover()`
- `SuiteResult` return type annotations on all suite `run()` methods

### Bug Fixes
- Double-curly-brace rendering in audit report navigation CSS
- CancelledError propagation in HTTP transport fallback — timeouts on Streamable HTTP no longer prevent SSE fallback

## 0.3.0 (2026-04-30)

### Features
- **Security suite** — 5 offline checks scanning tool descriptions for vulnerabilities:
  - Prompt injection patterns (IMPORTANT tags, IGNORE PREVIOUS, hidden instructions, imperatives)
  - Data exfiltration references (sensitive file paths, credential-reading instructions)
  - Cross-tool manipulation (tool shadowing, override instructions)
  - Suspicious encoding (base64-encoded instructions, zero-width characters, HTML entities)
  - Tool pin verification for rug pull detection
- `halflist pin` command — snapshot tool definition SHA-256 hashes for change detection
  - Stores pins in `~/.halflist/pins/<server-name>.json`
  - `--verify-pins` flag on `check` and `audit` to compare against saved snapshot
  - Custom output path via `-o`
- **HTML report generation** — `halflist report --format html`
  - Self-contained single file with inline CSS, no external dependencies
  - Dark theme, SVG donut gauge for score, CSS-only collapsible suite sections
  - Horizontal bar charts for benchmark latency with color coding
  - Supports all three report types: check, bench, audit

### Improvements
- Warmup failure detection in benchmarks — tools where all warmup calls fail are reported as "skipped (args rejected)" instead of "all failed"
  - Terminal: dim styled row; JSON: `"skipped": true, "skip_reason": "all warmup calls failed"`
  - Summary line shows benchmarked and skipped counts separately
- Score suppressed on filtered suite runs (`--suite`) — partial runs don't represent full server health
  - Terminal verdict shows PASS/FAIL without score; JSON still includes computed score
  - Full check (no filter) and audit always show score
- Sub-millisecond latencies display as `<1ms` instead of `0ms` across terminal, markdown, and HTML
- Imperative sentence threshold raised from 5 to 8 to reduce false positives on legitimate servers
- Cross-tool manipulation patterns split into specific (per-tool-name) and generic (once-per-tool) to eliminate false positive multiplication
- `benchmarked_count` and `total_calls` in bench/audit reports now exclude skipped tools

### Bug Fixes
- Pin file structure mismatch — security suite now correctly reads nested `tool_hashes` from PinData format
- Server names containing `/` no longer crash pin file operations — sanitized to `_` in file paths
- Cross-tool manipulation no longer reports N-1 false positives for generic patterns
- `BenchLiveProgress` handles skipped tools without crashing

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
