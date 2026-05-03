from __future__ import annotations

from halflist.models import SuiteResult
from halflist.suites.base import CheckSuite


class ResourcesSuite(CheckSuite):
    name = "resources"

    async def run(self) -> SuiteResult:
        start = self.measure()

        if not self.client.has_capability("resources"):
            self.record("resources/list returns valid array", "SKIP", "Server does not advertise resources capability")
            return self.build_result((self.measure() - start) * 1000)

        try:
            resources = await self.client.list_resources()
        except Exception as e:
            self.record("resources/list returns valid array", "FAIL", f"Error: {e}")
            return self.build_result((self.measure() - start) * 1000)

        self.record("resources/list returns valid array", "PASS", f"{len(resources)} resources")

        if len(resources) == 0:
            self.record("At least 1 resource exists", "WARN", "No resources found")
            return self.build_result((self.measure() - start) * 1000)

        self.record("At least 1 resource exists", "PASS", f"{len(resources)} resources")

        # Check every resource has uri
        missing_uri: list[str] = []
        for i, r in enumerate(resources):
            if not getattr(r, "uri", None):
                missing_uri.append(f"resource[{i}]")
        if missing_uri:
            self.record("Every resource has uri", "FAIL", f"Missing uri: {', '.join(missing_uri)}")
        else:
            self.record("Every resource has uri", "PASS")

        # Check every resource has name
        missing_name: list[str] = []
        for r in resources:
            if not getattr(r, "name", None):
                missing_name.append(str(r.uri))
        if missing_name:
            self.record("Every resource has name", "WARN", f"Missing name: {', '.join(missing_name[:3])}")
        else:
            self.record("Every resource has name", "PASS")

        # Read the first resource
        first = resources[0]
        try:
            t0 = self.measure()
            read_result = await self.client.read_resource(str(first.uri))
            dur = (self.measure() - t0) * 1000
        except Exception as e:
            self.record("resources/read returns valid content", "FAIL", f"Error reading {first.uri}: {e}")
            return self.build_result((self.measure() - start) * 1000)

        contents = read_result.contents
        if not contents:
            self.record("resources/read returns valid content", "FAIL", "Empty contents array")
            return self.build_result((self.measure() - start) * 1000)

        self.record("resources/read returns valid content", "PASS", f"{len(contents)} items, {dur:.0f}ms")

        # Check each content item has uri
        missing_content_uri: list[int] = []
        for i, c in enumerate(contents):
            if not getattr(c, "uri", None):
                missing_content_uri.append(i)
        if missing_content_uri:
            self.record("Each content item has uri", "FAIL", f"Missing uri at index: {missing_content_uri}")
        else:
            self.record("Each content item has uri", "PASS")

        # Check each content item has text or blob
        missing_content: list[int] = []
        for i, c in enumerate(contents):
            has_text = getattr(c, "text", None) is not None
            has_blob = getattr(c, "blob", None) is not None
            if not has_text and not has_blob:
                missing_content.append(i)
        if missing_content:
            self.record("Each content item has text or blob", "FAIL", f"Missing at index: {missing_content}")
        else:
            self.record("Each content item has text or blob", "PASS")

        # Check mimeType format if present
        bad_mime: list[str] = []
        for r in resources:
            mt = getattr(r, "mimeType", None)
            if mt is not None and "/" not in mt:
                bad_mime.append(f"{getattr(r, 'name', None) or r.uri}: {mt}")
        if bad_mime:
            self.record("mimeType is valid format", "WARN", f"Invalid: {', '.join(bad_mime)}")
        else:
            self.record("mimeType is valid format", "PASS")

        return self.build_result((self.measure() - start) * 1000)
