from __future__ import annotations

from halflist.models import SuiteResult
from halflist.suites.base import CheckSuite


class PromptsSuite(CheckSuite):
    name = "prompts"

    async def run(self) -> SuiteResult:
        start = self.measure()

        if not self.client.has_capability("prompts"):
            self.record(
                "prompts/list returns valid array",
                "SKIP",
                "Server does not advertise prompts capability",
            )
            return self.build_result((self.measure() - start) * 1000)

        try:
            prompts = await self.client.list_prompts()
        except Exception as e:
            self.record("prompts/list returns valid array", "FAIL", f"Error: {e}")
            return self.build_result((self.measure() - start) * 1000)

        self.record("prompts/list returns valid array", "PASS", f"{len(prompts)} prompts")

        if len(prompts) == 0:
            self.record("At least 1 prompt exists", "WARN", "No prompts found")
            return self.build_result((self.measure() - start) * 1000)

        self.record("At least 1 prompt exists", "PASS", f"{len(prompts)} prompts")

        # Check every prompt has name
        missing_name: list[int] = []
        for i, p in enumerate(prompts):
            if not getattr(p, "name", None):
                missing_name.append(i)
        if missing_name:
            self.record("Every prompt has name", "FAIL", f"Missing name at index: {missing_name}")
        else:
            self.record("Every prompt has name", "PASS")

        # Check every prompt has description
        missing_desc: list[str] = []
        for p in prompts:
            if not getattr(p, "description", None):
                missing_desc.append(p.name or "?")
        if missing_desc:
            self.record(
                "Every prompt has description",
                "WARN",
                f"Missing description: {', '.join(missing_desc[:3])}",
            )
        else:
            self.record("Every prompt has description", "PASS")

        # Call get_prompt on the first prompt
        first = prompts[0]
        dummy_args: dict[str, str] = {}
        for arg in first.arguments or []:
            dummy_args[arg.name] = "test"

        try:
            t0 = self.measure()
            result = await self.client.get_prompt(first.name, dummy_args or None)
            dur = (self.measure() - t0) * 1000
        except Exception as e:
            self.record("prompts/get returns valid messages", "FAIL", f"Error: {e}")
            return self.build_result((self.measure() - start) * 1000)

        messages = result.messages
        if not messages:
            self.record("prompts/get returns valid messages", "FAIL", "Empty messages array")
            return self.build_result((self.measure() - start) * 1000)

        self.record(
            "prompts/get returns valid messages", "PASS", f"{len(messages)} messages, {dur:.0f}ms"
        )

        # Check each message has role
        missing_role: list[int] = []
        for i, m in enumerate(messages):
            if not getattr(m, "role", None):
                missing_role.append(i)
        if missing_role:
            self.record("Each message has role", "FAIL", f"Missing role at index: {missing_role}")
        else:
            self.record("Each message has role", "PASS")

        # Check each message has content
        missing_content: list[int] = []
        for i, m in enumerate(messages):
            if getattr(m, "content", None) is None:
                missing_content.append(i)
        if missing_content:
            self.record(
                "Each message has content", "FAIL", f"Missing content at index: {missing_content}"
            )
        else:
            self.record("Each message has content", "PASS")

        return self.build_result((self.measure() - start) * 1000)
