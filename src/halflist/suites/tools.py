from __future__ import annotations

import re

from halflist.constants import TOOL_NAME_PATTERN
from halflist.models import SuiteResult
from halflist.schema_gen import generate_args
from halflist.suites.base import CheckSuite


class ToolsSuite(CheckSuite):
    name = "tools"

    async def run(self) -> SuiteResult:
        start = self.measure()

        try:
            tools = await self.client.list_tools()
        except Exception as e:
            self.record("tools/list returns valid array", "FAIL", str(e))
            return self.build_result((self.measure() - start) * 1000)

        self.record("tools/list returns valid array", "PASS", f"{len(tools)} tools")

        if len(tools) == 0:
            self.record("At least 1 tool exists", "WARN", "No tools found")
            return self.build_result((self.measure() - start) * 1000)
        else:
            self.record("At least 1 tool exists", "PASS", f"{len(tools)} tools")

        all_have_name = all(t.name for t in tools)
        if all_have_name:
            self.record("Every tool has a non-empty name", "PASS")
        else:
            self.record("Every tool has a non-empty name", "FAIL", "Some tools have empty names")

        absent_desc = [t.name for t in tools if t.description is None]
        empty_desc = [t.name for t in tools if t.description is not None and t.description == ""]
        if absent_desc or empty_desc:
            parts = []
            if absent_desc:
                parts.append(f"{len(absent_desc)} with no description: {', '.join(absent_desc)}")
            if empty_desc:
                parts.append(f"{len(empty_desc)} with empty description: {', '.join(empty_desc)}")
            self.record(
                "Every tool has a description",
                "WARN",
                f"{len(absent_desc) + len(empty_desc)} tool(s) — {'; '.join(parts)}",
            )
        else:
            self.record("Every tool has a description", "PASS")

        bad_schema = [t.name for t in tools if t.inputSchema.get("type") != "object"]
        if bad_schema:
            self.record(
                'inputSchema contains "type": "object"',
                "FAIL",
                f"Invalid for: {', '.join(bad_schema)}",
            )
        else:
            self.record('inputSchema contains "type": "object"', "PASS")

        names = [t.name for t in tools]
        if len(names) != len(set(names)):
            self.record("No duplicate tool names", "FAIL", "Duplicate names found")
        else:
            self.record("No duplicate tool names", "PASS")

        bad_names = [n for n in names if not re.match(TOOL_NAME_PATTERN, n)]
        if bad_names:
            self.record(
                "Tool names follow recommended pattern",
                "WARN",
                f"Non-conforming: {', '.join(bad_names)}",
            )
        else:
            self.record("Tool names follow recommended pattern", "PASS")

        first_tool = tools[0]
        args = generate_args(first_tool.inputSchema)
        call_result = None
        try:
            t0 = self.measure()
            call_result = await self.client.call_tool(first_tool.name, args)
            dur = (self.measure() - t0) * 1000
            if hasattr(call_result, "content"):
                self.record(
                    f"tools/call {first_tool.name} returns valid response",
                    "PASS",
                    f"{dur:.0f}ms",
                )
            else:
                self.record(
                    f"tools/call {first_tool.name} returns valid response",
                    "FAIL",
                    "Response missing content field",
                )
        except Exception as e:
            self.record(
                f"tools/call {first_tool.name} returns valid response",
                "FAIL",
                str(e),
            )

        try:
            t0 = self.measure()
            empty_result = await self.client.call_tool(first_tool.name, {})
            dur = (self.measure() - t0) * 1000
            self.record(
                f"tools/call {first_tool.name} with empty args handles gracefully",
                "PASS",
                f"isError={getattr(empty_result, 'isError', False)}, {dur:.0f}ms",
            )
        except Exception as e:
            self.record(
                f"tools/call {first_tool.name} with empty args handles gracefully",
                "FAIL",
                f"Exception: {e}",
            )

        if call_result is not None and hasattr(call_result, "content"):
            content = call_result.content
            if isinstance(content, list):
                self.record("Response content is a list", "PASS")
                all_typed = all(hasattr(item, "type") for item in content)
                if all_typed:
                    self.record("Each content item has a type field", "PASS")
                else:
                    self.record("Each content item has a type field", "FAIL", "Missing type on some items")
            else:
                self.record("Response content is a list", "FAIL", f"Got {type(content).__name__}")
                self.record("Each content item has a type field", "SKIP", "Content not a list")
        else:
            self.record("Response content is a list", "SKIP", "No successful call result")
            self.record("Each content item has a type field", "SKIP", "No successful call result")

        return self.build_result((self.measure() - start) * 1000)
