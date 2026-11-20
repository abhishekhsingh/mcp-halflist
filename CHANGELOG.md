# Changelog

## v1.1.2 (2026-11-20)

### Changes
- Package metadata: more keywords, Python 3.10 to 3.12 and Security classifiers, and Changelog and GitHub Action links on PyPI

## v1.1.1 (2026-11-15)

### Bug Fixes
- `--no-browser` login no longer aborts when stdin is closed or empty (CI, `/dev/null`, or a stray Enter key). Empty input is ignored and the callback server completes the login, as before when you open the printed URL
- The process now exits as soon as the login has finished. Before, it stayed alive until stdin was closed or a key was pressed
- The authorization URL printed by `--no-browser` is no longer broken across lines at the terminal width, so it can be copied as one piece

### Internal
- Regression tests cover closed, empty and unreadable stdin, pasting the callback URL, the process exiting after login, and the printed URL

## v1.1.0 (2026-11-15)

### Changes
- **halflist now runs on `mcp` 2.x**: the dependency is `mcp>=2.3.0,<3` (it was `<2`). Every command, option, exit code and report format behaves as before. The servers you test can be built with any MCP SDK or language; this only changes the SDK halflist itself uses. `mcp` 1.x is no longer supported, so stay on halflist 1.0.x if you need it
- `httpx2` is now a declared dependency, because halflist passes HTTP clients and auth providers to the `mcp` 2 SDK. `httpx` is still used for the OAuth client-credentials token request

### Bug Fixes
- OAuth PKCE login passes the RFC 9207 `iss` redirect parameter to the SDK, including when the callback URL is pasted in `--no-browser` mode, because the `mcp` 2 SDK validates it

### Notes from the SDK upgrade
- A redirect whose `iss` does not match the authorization server is now rejected (the `mcp` 2 SDK checks it)
- Newly registered OAuth clients are stored with an extra `application_type` field in `~/.halflist/tokens/`. Token files written by earlier versions keep working, and files written by this version are readable by earlier versions
- When an HTTP server is unreachable, the SSE part of the connection error now reads "All connection attempts failed" instead of "unhandled errors in a TaskGroup". The exit code is unchanged

### Internal
- Test servers use the `mcp` 2 server API and regression tests cover the issuer handling
- Before release, the output of check, audit, bench, pin and watch was compared with 1.0.2 across stdio and HTTP servers, with no differences other than the ones listed above

## v1.0.2 (2026-11-14)

### Bug Fixes
- **Security scan false positives**: the data exfiltration rules matched inside identifiers and longer words. `include...secret` matched the environment variable name `GET_ENV_INCLUDE_SECRETS` in the description of the reference server's `get-env` tool, which was reported as THREAT DETECTED, and `upload...key` matched "keyboard". The verb must now be a whole word (inflections such as `reads` or `sending` still match) and the sensitive noun must not be part of a longer word. Names such as `api_key` and `client_secret` are still caught
- Inflected forms of "include", for example "Including the secret in each call", are now detected

### Internal
- Regression tests cover both the false positives and the instructions that must still be reported

## v1.0.1 (2026-11-14)

### Bug Fixes
- **Dependency cap**: `mcp` is now constrained to `<2`. `mcp` 2.x renamed `FastMCP` and changed the client result types, which made a fresh `pip install mcp-halflist` resolve to a version halflist cannot talk to (`'InitializeResult' object has no attribute 'serverInfo'`). Support for `mcp` 2.x is a separate piece of work
- **Version string**: `halflist --version`, the terminal banner and the `version` field in JSON reports showed `0.4.0`. The version now has a single source (`src/halflist/__init__.py`, read by the build)
- **Terminal output crash**: server-controlled text (server name, tool names, findings, error messages) was interpreted as Rich markup, so a name such as `foo[/x]` raised `MarkupError` and aborted the run. All such text is now escaped
- **`Authorization` header detection** is case-insensitive. `--header "authorization: ..."` now suppresses automatic PKCE like `Authorization` does, and an OAuth client-credentials token replaces any case variant instead of sending two headers
- **`rich` is now a declared dependency** (it was only installed transitively through `typer`)
- `--format` help text for `check`, `bench` and `audit` now lists `junit`

### Features
- **`--pin-file`** on `check` and `audit`: verify tool pins against a specific file (implies `--verify-pins`), so a pin file committed to a repo can be used in CI. A missing file exits with code 3

### Documentation
- JUnit output is now documented in `docs/output-formats.md`
- CI examples write JUnit output with shell redirection (`> results.xml`). `-o/--output` exists only on `report` and `pin`

### Internal
- Tests run with an isolated `HOME`, so they no longer write to the real `~/.halflist`
- Ruff lint rules are pinned in `pyproject.toml` so CI does not change when ruff widens its default rule set
- Regression tests added for every fix above

## v1.0.0 (2026-05-29)

### Features
- **OAuth2 Authorization Code + PKCE** (Tier 3 auth): automatic browser-based authentication for HTTP servers that return 401
  - Uses MCP SDK's built-in `OAuthClientProvider`: handles PRM discovery (RFC 9728), AS metadata (RFC 8414), dynamic client registration (RFC 7591), PKCE (RFC 7636), token refresh, and resource indicators (RFC 8707)
  - `CallbackServer`: localhost HTTP server on 127.0.0.1 (ports 3030-3039) to capture OAuth redirects
  - `FileTokenStorage`: persistent token/client storage at `~/.halflist/tokens/` with 0o600/0o700 permissions
  - New flags on all HTTP-capable commands: `--no-browser`, `--clear-tokens`, `--callback-port`, `--no-auth`
  - Headless mode (`--no-browser`): prints auth URL to stderr, races between callback server and stdin URL paste
  - Auth tier precedence: static headers (Tier 1) → client_credentials (Tier 2) → PKCE (Tier 3) → no-auth
  - Zero new dependencies: uses stdlib `webbrowser`, `http.server`, `threading`, `hashlib`
- **Per-call timeout for benchmarks**: each `tools/call` in bench and audit is now capped by `--timeout` (default 30s), preventing indefinite hangs on tools that block on bad arguments
- **Custom tool arguments** (`--args-file`): JSON file mapping tool names to argument objects, used for benchmarks and smoke tests
  - Available on `check`, `bench`, and `audit` commands
  - Falls back to schema-based dummy arg generation for tools not in the file

- **Debug logging** (`--debug`): multi-layer request/response logging for debugging MCP traffic
  - Layer 1: MCP operation logging (→ initialize, ← tools/list, etc.)
  - Layer 2: HTTP wire logging via httpx event hooks (request/response with masked credentials)
  - Layer 3: SDK internal logging (mcp, httpx, httpcore loggers)
  - `--debug-log <file>` to write debug output to a file
  - `HALFLIST_LOG_LEVEL` env var for CI environments
  - Available on all 6 commands
- **JUnit XML output** (`--format junit`): CI-native test reporting for GitHub Actions, GitLab, Jenkins
  - Available on `check`, `bench`, `audit` commands and `report` post-processing
  - WARN checks mapped to `<failure type="WARN">` for CI visibility
  - Bench results include p50/p95/p99 as `<property>` elements
  - `[output] format = "junit"` and `[report] format = "junit"` in halflist.toml
- **halflist.toml config file**: optional TOML config to replace repeated CLI flags
  - Auto-discovered from cwd (`halflist.toml`, `.halflist.toml`) or `~/.halflist/config.toml`
  - Explicit path via `--config` flag on all 6 commands
  - `${ENV_VAR}` expansion in all string values (secrets, URLs, file paths)
  - CLI flags always override config; config overrides defaults
  - Warns on unknown keys (typos) without crashing
  - `tomli` fallback for Python 3.10 compatibility

### CI/CD
- CI: GitHub Actions workflow with Python 3.10/3.11/3.12 matrix, ruff lint + format check, pytest
- Publish: PyPI trusted publishing via GitHub Releases (no API token needed)

### Improvements
- Security check messages now include thresholds, matched text snippets, and actionable context
- Security findings expanded with `→` prefix in terminal output (each finding on its own line for FAIL/WARN checks)

## 0.4.0 (2026-05-03)

### Features
- **HTTP transport**: `--http` flag with Streamable HTTP / SSE automatic fallback
- **Authentication flags**: `--header`, `--oauth-token-url`, `--oauth-client-id`, `--oauth-client-secret`, `--oauth-scope` on all server-connecting commands
- **Resources suite** (8 checks): resources/list validation, uri/name checks, resources/read smoke test, content item validation, mimeType format
- **Prompts suite** (7 checks): prompts/list validation, name/description checks, prompts/get smoke test, message role/content validation

### Visual
- **Terminal aesthetic overhaul**: green-on-black theme, monospace styling, scan line animation in HTML reports
- **HTML report makeover**: terminal-inspired dark theme with CSS custom properties, fixed nav on audit reports, print styles
- **Colored status dots** in bench tables: green (fast), yellow (moderate), red (slow) based on p99 latency
- **HALFLIST logo** in HTML reports: clean letter-spaced text replacing box-drawing ASCII art

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
- CancelledError propagation in HTTP transport fallback: timeouts on Streamable HTTP no longer prevent SSE fallback

## 0.3.0 (2026-04-30)

### Features
- **Security suite**: 5 offline checks scanning tool descriptions for vulnerabilities:
  - Prompt injection patterns (IMPORTANT tags, IGNORE PREVIOUS, hidden instructions, imperatives)
  - Data exfiltration references (sensitive file paths, credential-reading instructions)
  - Cross-tool manipulation (tool shadowing, override instructions)
  - Suspicious encoding (base64-encoded instructions, zero-width characters, HTML entities)
  - Tool pin verification for rug pull detection
- `halflist pin` command: snapshot tool definition SHA-256 hashes for change detection
  - Stores pins in `~/.halflist/pins/<server-name>.json`
  - `--verify-pins` flag on `check` and `audit` to compare against saved snapshot
  - Custom output path via `-o`
- **HTML report generation**: `halflist report --format html`
  - Self-contained single file with inline CSS, no external dependencies
  - Dark theme, SVG donut gauge for score, CSS-only collapsible suite sections
  - Horizontal bar charts for benchmark latency with color coding
  - Supports all three report types: check, bench, audit

### Improvements
- Warmup failure detection in benchmarks: tools where all warmup calls fail are reported as "skipped (args rejected)" instead of "all failed"
  - Terminal: dim styled row; JSON: `"skipped": true, "skip_reason": "all warmup calls failed"`
  - Summary line shows benchmarked and skipped counts separately
- Score suppressed on filtered suite runs (`--suite`): partial runs don't represent full server health
  - Terminal verdict shows PASS/FAIL without score; JSON still includes computed score
  - Full check (no filter) and audit always show score
- Sub-millisecond latencies display as `<1ms` instead of `0ms` across terminal, markdown, and HTML
- Imperative sentence threshold raised from 5 to 8 to reduce false positives on legitimate servers
- Cross-tool manipulation patterns split into specific (per-tool-name) and generic (once-per-tool) to eliminate false positive multiplication
- `benchmarked_count` and `total_calls` in bench/audit reports now exclude skipped tools

### Bug Fixes
- Pin file structure mismatch: security suite now correctly reads nested `tool_hashes` from PinData format
- Server names containing `/` no longer crash pin file operations (sanitized to `_` in file paths)
- Cross-tool manipulation no longer reports N-1 false positives for generic patterns
- `BenchLiveProgress` handles skipped tools without crashing

## 0.2.0 (2026-04-28)

### Added
- `halflist audit`: full conformance check + benchmark in one shot
  - Runs all suites + benchmarks all tools with a single connection
  - Combined `AuditReport` JSON with both suites and benchmarks
  - `halflist report` auto-detects audit JSON for markdown generation
- `halflist bench`: latency benchmarking per tool with p50/p95/p99 percentiles
  - `--tool` filter (repeatable), `--all`, `--iterations/-n`, `--warmup/-w`
  - Rich terminal output with live progress and results table
  - JSON output (`--format json`)
- `halflist watch`: continuous health monitoring with JSONL output
  - `--interval/-i`, `--count/-c`, `--log/-l` for file logging
  - Per-probe status: ok / degraded / down
- `halflist report`: generate markdown or SVG badge from JSON output
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
