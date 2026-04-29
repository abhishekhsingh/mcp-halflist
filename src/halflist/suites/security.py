from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Callable

from mcp import types

from halflist.client import HalflistClient
from halflist.models import SuiteResult
from halflist.suites.base import CheckSuite

# ── Check 1: Prompt injection patterns ────────────────────────────────────────

_INJECTION_FAIL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"</?IMPORTANT>", re.IGNORECASE), "<IMPORTANT> tags"),
    (re.compile(r"IGNORE\s+(ALL\s+)?PREVIOUS\s+INSTRUCTIONS", re.IGNORECASE), "IGNORE PREVIOUS INSTRUCTIONS"),
    (re.compile(r"^system:", re.IGNORECASE | re.MULTILINE), "system: directive"),
    (re.compile(r"^\[SYSTEM\]", re.IGNORECASE | re.MULTILINE), "[SYSTEM] directive"),
    (
        re.compile(
            r"You\s+must\s+(read|send|upload|exfiltrate|leak|transmit|forward|copy)\b",
            re.IGNORECASE,
        ),
        "You must + action verb",
    ),
    (
        re.compile(
            r"You\s+should\s+(read|send|upload|exfiltrate|leak|transmit|forward|copy)\b",
            re.IGNORECASE,
        ),
        "You should + action verb",
    ),
    (re.compile(r"Do\s+not\s+tell\s+the\s+user", re.IGNORECASE), "Do not tell the user"),
    (re.compile(r"Do\s+not\s+inform", re.IGNORECASE), "Do not inform"),
    (re.compile(r"Hide\s+this\s+from", re.IGNORECASE), "Hide this from"),
    (
        re.compile(
            r"Before\s+using\s+this\s+tool.*?(file|credential|read|access|key|token|secret)",
            re.IGNORECASE | re.DOTALL,
        ),
        "Before using this tool + credential access",
    ),
    (re.compile(r"<HIDDEN>", re.IGNORECASE), "<HIDDEN> tag"),
    (re.compile(r"<!--.*?-->", re.DOTALL), "HTML comment"),
]

_INJECTION_WARN_DESC_LENGTH = 2000
_INJECTION_WARN_IMPERATIVE_THRESHOLD = 8

_IMPERATIVE_VERB_PATTERN: re.Pattern[str] = re.compile(
    r"(?:^|\.\s+)[A-Z][a-z]+\s",
    re.MULTILINE,
)

# ── Check 2: Data exfiltration references ─────────────────────────────────────

_EXFIL_FAIL_PATH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"~/?\.ssh\b"), "~/.ssh"),
    (re.compile(r"\bid_rsa\b"), "id_rsa"),
    (re.compile(r"\bid_ed25519\b"), "id_ed25519"),
    (re.compile(r"~/?\.env\b"), "~/.env"),
    (re.compile(r"(?<!\w)\.env\b"), ".env"),
    (re.compile(r"~/?\.aws/credentials\b"), "~/.aws/credentials"),
    (re.compile(r"~/?\.gnupg\b"), "~/.gnupg"),
    (re.compile(r"~/?\.config\b"), "~/.config"),
    (re.compile(r"/etc/passwd\b"), "/etc/passwd"),
    (re.compile(r"/etc/shadow\b"), "/etc/shadow"),
]

_EXFIL_FAIL_IMPERATIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"read.*password", re.IGNORECASE | re.DOTALL), "read...password"),
    (re.compile(r"send.*token", re.IGNORECASE | re.DOTALL), "send...token"),
    (re.compile(r"upload.*key", re.IGNORECASE | re.DOTALL), "upload...key"),
    (re.compile(r"pass.*credentials", re.IGNORECASE | re.DOTALL), "pass...credentials"),
    (re.compile(r"include.*secret", re.IGNORECASE | re.DOTALL), "include...secret"),
    (re.compile(r"attach.*cookie", re.IGNORECASE | re.DOTALL), "attach...cookie"),
]

_EXFIL_WARN_HTTP: re.Pattern[str] = re.compile(r"http://")

_EXFIL_WARN_SENSITIVE_KEYWORDS: re.Pattern[str] = re.compile(
    r"\b(password|secret|token|credential|api_key)\b", re.IGNORECASE
)

# ── Check 3: Cross-tool manipulation ─────────────────────────────────────────

_CROSS_TOOL_SPECIFIC_TEMPLATES: list[str] = [
    r"when\s+using\s+{tool}",
    r"instead\s+of\s+{tool}",
    r"override\s+{tool}",
    r"replace\s+{tool}",
    r"do\s+not\s+use\s+{tool}",
]

_CROSS_TOOL_GENERIC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"use\s+this\s+tool\s+instead\s+of", re.IGNORECASE), "instructs to use instead of other tools"),
    (re.compile(r"always\s+call\s+this\s+(before|first)", re.IGNORECASE), "instructs to always call first"),
]

# ── Check 4: Suspicious encoding ─────────────────────────────────────────────

_BASE64_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")

_ZERO_WIDTH_CHARS: str = "".join([
    chr(0x200B),
    chr(0x200C),
    chr(0x200D),
    chr(0xFEFF),
    chr(0x00AD),
])
_ZERO_WIDTH_PATTERN: re.Pattern[str] = re.compile(f"[{_ZERO_WIDTH_CHARS}]")

_INSTRUCTION_WORDS: re.Pattern[str] = re.compile(
    r"\b(ignore|override|system|execute|run|send|read|upload|password|token|secret)\b",
    re.IGNORECASE,
)

_HTML_ENTITY_PATTERN: re.Pattern[str] = re.compile(
    r"&lt;|&gt;|&#x[0-9a-fA-F]+;?|&#[0-9]+;?"
)


def _get_description(tool: types.Tool) -> str | None:
    if tool.description is None or tool.description.strip() == "":
        return None
    return tool.description


class SecuritySuite(CheckSuite):
    name = "security"

    def __init__(
        self,
        client: HalflistClient,
        on_check: Callable[..., None] | None = None,
        *,
        verify_pins: bool = False,
        pins_dir: Path | None = None,
    ) -> None:
        super().__init__(client, on_check)
        self._verify_pins = verify_pins
        self._pins_dir = pins_dir or Path.home() / ".halflist" / "pins"

    async def run(self) -> SuiteResult:
        start = self.measure()

        try:
            tools = await self.client.list_tools()
        except Exception as e:
            self.record("Prompt injection scan", "FAIL", f"Could not list tools: {e}")
            return self.build_result((self.measure() - start) * 1000)

        self._check_prompt_injection(tools)
        self._check_data_exfiltration(tools)
        self._check_cross_tool_manipulation(tools)
        self._check_suspicious_encoding(tools)
        self._check_tool_pins(tools)

        return self.build_result((self.measure() - start) * 1000)

    def _check_prompt_injection(self, tools: list[types.Tool]) -> None:
        failures: list[str] = []
        warnings: list[str] = []

        for tool in tools:
            desc = _get_description(tool)
            if desc is None:
                continue

            for pattern, label in _INJECTION_FAIL_PATTERNS:
                if pattern.search(desc):
                    failures.append(f"{tool.name}: {label}")

            if len(desc) > _INJECTION_WARN_DESC_LENGTH:
                warnings.append(f"{tool.name}: description length {len(desc)} chars")

            imperative_count = len(_IMPERATIVE_VERB_PATTERN.findall(desc))
            if imperative_count > _INJECTION_WARN_IMPERATIVE_THRESHOLD:
                warnings.append(f"{tool.name}: {imperative_count} imperative sentences")

        if failures:
            self.record(
                "Prompt injection scan",
                "FAIL",
                "; ".join(failures),
            )
        elif warnings:
            self.record(
                "Prompt injection scan",
                "WARN",
                "; ".join(warnings),
            )
        else:
            self.record("Prompt injection scan", "PASS")

    def _check_data_exfiltration(self, tools: list[types.Tool]) -> None:
        failures: list[str] = []
        warnings: list[str] = []

        for tool in tools:
            desc = _get_description(tool)
            if desc is None:
                continue

            for pattern, label in _EXFIL_FAIL_PATH_PATTERNS:
                if pattern.search(desc):
                    failures.append(f"{tool.name}: references {label}")

            for pattern, label in _EXFIL_FAIL_IMPERATIVE_PATTERNS:
                if pattern.search(desc):
                    failures.append(f"{tool.name}: {label}")

            if _EXFIL_WARN_HTTP.search(desc):
                warnings.append(f"{tool.name}: contains http:// URL")

            if _EXFIL_WARN_SENSITIVE_KEYWORDS.search(desc):
                has_imperative = any(
                    p.search(desc) for p, _ in _EXFIL_FAIL_IMPERATIVE_PATTERNS
                )
                if not has_imperative:
                    warnings.append(f"{tool.name}: mentions sensitive keyword")

        if failures:
            self.record(
                "Data exfiltration references",
                "FAIL",
                "; ".join(failures),
            )
        elif warnings:
            self.record(
                "Data exfiltration references",
                "WARN",
                "; ".join(warnings),
            )
        else:
            self.record("Data exfiltration references", "PASS")

    def _check_cross_tool_manipulation(self, tools: list[types.Tool]) -> None:
        tool_names: set[str] = {t.name for t in tools}
        failures: list[str] = []

        for tool in tools:
            desc = _get_description(tool)
            if desc is None:
                continue

            other_names = tool_names - {tool.name}
            for other in other_names:
                escaped = re.escape(other)
                for template in _CROSS_TOOL_SPECIFIC_TEMPLATES:
                    pattern_str = template.format(tool=escaped)
                    if re.search(pattern_str, desc, re.IGNORECASE):
                        failures.append(f"{tool.name}: manipulates {other}")
                        break

            for pattern, label in _CROSS_TOOL_GENERIC_PATTERNS:
                if pattern.search(desc):
                    failures.append(f"{tool.name}: {label}")
                    break

        if failures:
            self.record(
                "Cross-tool manipulation",
                "FAIL",
                "; ".join(failures),
            )
        else:
            self.record("Cross-tool manipulation", "PASS")

    def _check_suspicious_encoding(self, tools: list[types.Tool]) -> None:
        failures: list[str] = []
        warnings: list[str] = []

        for tool in tools:
            desc = _get_description(tool)
            if desc is None:
                continue

            for match in _BASE64_PATTERN.finditer(desc):
                candidate = match.group()
                try:
                    decoded = base64.b64decode(candidate).decode("ascii")
                    if _INSTRUCTION_WORDS.search(decoded):
                        failures.append(f"{tool.name}: base64 decodes to instructions")
                        break
                except Exception:
                    continue

            if _ZERO_WIDTH_PATTERN.search(desc):
                failures.append(f"{tool.name}: contains zero-width characters")

            if _HTML_ENTITY_PATTERN.search(desc):
                warnings.append(f"{tool.name}: contains HTML entities")

        if failures:
            self.record(
                "Suspicious encoding",
                "FAIL",
                "; ".join(failures),
            )
        elif warnings:
            self.record(
                "Suspicious encoding",
                "WARN",
                "; ".join(warnings),
            )
        else:
            self.record("Suspicious encoding", "PASS")

    def _check_tool_pins(self, tools: list[types.Tool]) -> None:
        if not self._verify_pins:
            self.record("Tool pin verification", "SKIP", "Pin verification not requested")
            return

        server_name = "unknown"
        if self.client.init_result and hasattr(self.client.init_result, "serverInfo"):
            server_name = self.client.init_result.serverInfo.name

        safe_name = server_name.replace("/", "_").replace("\\", "_")
        pin_file = self._pins_dir / f"{safe_name}.json"

        if not pin_file.exists():
            self.record(
                "Tool pin verification",
                "WARN",
                "No pins found, run halflist pin first",
            )
            return

        try:
            pin_data = json.loads(pin_file.read_text())
            pinned: dict[str, str] = pin_data.get("tool_hashes", pin_data)
        except Exception as e:
            self.record("Tool pin verification", "FAIL", f"Could not read pin file: {e}")
            return

        current_hashes: dict[str, str] = {}
        for t in tools:
            payload = json.dumps(
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema,
                },
                sort_keys=True,
            )
            current_hashes[t.name] = hashlib.sha256(payload.encode()).hexdigest()

        changed: list[str] = []
        added: list[str] = []
        removed: list[str] = []

        for name, current_hash in current_hashes.items():
            if name not in pinned:
                added.append(name)
            elif pinned[name] != current_hash:
                changed.append(name)

        for name in pinned:
            if name not in current_hashes:
                removed.append(name)

        if changed:
            self.record(
                "Tool pin verification",
                "FAIL",
                f"Hash changed: {', '.join(changed)}",
            )
        elif added or removed:
            parts: list[str] = []
            if added:
                parts.append(f"New tools: {', '.join(added)}")
            if removed:
                parts.append(f"Removed tools: {', '.join(removed)}")
            self.record(
                "Tool pin verification",
                "WARN",
                "; ".join(parts),
            )
        else:
            self.record("Tool pin verification", "PASS")
