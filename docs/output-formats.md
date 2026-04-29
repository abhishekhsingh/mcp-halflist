# Output Formats

halflist supports five output formats across its commands.

## Terminal (default)

All commands default to rich, colored terminal output.

### Three-Phase UX

1. **Connection** — spinner while connecting, then server name, version, and tool count
2. **Progress** — live-updating display showing check/benchmark progress with status symbols
3. **Report** — final scored report with suite breakdown

### Compact vs Verbose

By default, the terminal shows a compact view: status symbols per suite and details only for non-passing checks.

```
security ──────────────────────────────── 4/5 passed
  ✓✓✓✓—
  — Tool pin verification ··················· Pin verification not requested
```

With `--verbose` (`-v`), every check is shown with its result:

```
security ──────────────────────────────── 4/5 passed
  ✓ Prompt injection scan ··················· PASS
  ✓ Data exfiltration references ············ PASS
  ✓ Cross-tool manipulation ················· PASS
  ✓ Suspicious encoding ····················· PASS
  — Tool pin verification ··················· Pin verification not requested
```

### Status Symbols

| Symbol | Color | Meaning |
|--------|-------|---------|
| `✓` | Green | PASS |
| `✗` | Red | FAIL |
| `⚠` | Yellow | WARN |
| `—` | Dim | SKIP |

### Latency Display

Sub-millisecond latencies display as `<1ms` instead of `0ms`.

## JSON (`--format json`)

Available on `check`, `bench`, and `audit` commands.

- Full structured report on **stdout** (clean, parseable)
- Progress and connection info on **stderr** (if stderr is a TTY)
- Server stderr output is automatically suppressed

### JSON Models

**check** produces a `HalflistReport`:
```json
{
  "version": "0.3.0",
  "timestamp": "2026-04-29T...",
  "server_info": { "name": "...", "version": "..." },
  "transport": "stdio",
  "suites": [...],
  "score": 98,
  "total_passed": 21,
  "total_failed": 0,
  "total_warned": 0,
  "total_duration_ms": 45.2
}
```

**bench** produces a `BenchReport`:
```json
{
  "version": "0.3.0",
  "timestamp": "2026-04-29T...",
  "server_info": { "name": "...", "version": "..." },
  "transport": "stdio",
  "connection_ms": 1200.5,
  "discovery_ms": 4.8,
  "tool_count": 13,
  "benchmarked_count": 12,
  "iterations": 10,
  "warmup": 2,
  "benchmarks": [
    {
      "tool_name": "echo",
      "iterations": 10,
      "min_ms": 0.45, "max_ms": 1.2,
      "mean_ms": 0.72, "median_ms": 0.68,
      "p95_ms": 1.1, "p99_ms": 1.2,
      "errors": 0,
      "skipped": false,
      "skip_reason": null
    }
  ],
  "total_calls": 120,
  "total_duration_ms": 15200.0
}
```

Skipped tools have `"skipped": true` and `"skip_reason": "all warmup calls failed"` with `iterations` set to 0.

**audit** produces an `AuditReport` combining both suites and benchmarks.

### CI Integration

```bash
# Gate on exit code
halflist check --stdio "python3 my_server.py" --format json > report.json
if [ $? -ne 0 ]; then echo "Checks failed"; exit 1; fi

# Parse score with jq
SCORE=$(halflist check --stdio "python3 my_server.py" --format json | jq .score)
```

## Markdown (`halflist report`)

Generated from JSON via the `report` command. Default format.

```bash
halflist check --stdio "..." --format json > results.json
halflist report results.json
```

Produces markdown tables suitable for README files, PR comments, or documentation. Auto-detects whether the JSON is from check, bench, or audit.

Skipped benchmark tools show as `*skipped (args rejected)*` (italic) in the table.

## HTML (`halflist report --format html`)

Self-contained single HTML file with no external dependencies.

```bash
halflist report results.json --format html -o report.html
```

### Features

- **Dark theme** (`#0d1117` background) — easy on the eyes
- **SVG donut gauge** — visual score indicator (check and audit reports)
- **Collapsible suites** — CSS-only `<details>/<summary>`, no JavaScript
- **Per-check details** — status icon, check name, and message for every check
- **Benchmark bar charts** — horizontal bars colored by latency (green/yellow/red)
- **Responsive layout** — works on desktop and mobile
- **Inline CSS** — everything in one file, works offline, no CDN dependencies

Skipped benchmark tools appear as a dim, italic row spanning the full table.

HTML reports are generated for all three report types: check, bench, and audit.

See an [example HTML report](https://github.com/abhishekhsingh/mcp-halflist/blob/main/examples/audit-report.html) generated from the official MCP reference server.

## SVG Badge (`halflist report --badge`)

Shields.io-style SVG badge for embedding in README files.

```bash
halflist report results.json --badge -o badge.svg
```

- **Check/audit reports** — shows score (e.g., `MCP | 98/100`), colored green/yellow/red
- **Bench reports** — shows tool count and average p50 (e.g., `MCP bench | 5 tools · p50 avg 12ms`)

### Embedding in README

```markdown
![MCP Score](./badge.svg)
```

Or generate and commit in CI:

```bash
halflist audit --stdio "python3 my_server.py" --format json > audit.json
halflist report audit.json --badge -o badge.svg
git add badge.svg && git commit -m "Update MCP badge"
```

## Score Formula

The conformance score is computed from all check results:

| Status | Weight |
|--------|--------|
| PASS | 1.0 |
| WARN | 0.5 |
| SKIP | 0.5 |
| FAIL | 0.0 |

Score = (sum of weights / total checks) * 100, rounded to nearest integer.

**Score suppression:** When `--suite` is used to run a subset of suites, the score is suppressed in terminal output because a partial run doesn't represent full server health. The verdict (PASS/FAIL) is still shown. JSON output always includes the computed score. Audit always runs all suites, so the score is always shown.
