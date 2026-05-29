"""Test that the tools suite differentiates absent vs empty descriptions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from halflist.suites.tools import ToolsSuite


def _make_tool(name: str, description: str | None = "A tool") -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.inputSchema = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "required": ["x"],
    }
    return tool


@pytest.mark.asyncio
async def test_absent_description_produces_warn() -> None:
    client = MagicMock()
    client.list_tools = AsyncMock(
        return_value=[
            _make_tool("tool_a", description=None),
            _make_tool("tool_b", description="Good desc"),
        ]
    )
    call_result = MagicMock()
    call_result.content = [MagicMock(type="text")]
    call_result.isError = False
    client.call_tool = AsyncMock(return_value=call_result)

    suite = ToolsSuite(client)
    result = await suite.run()

    desc_check = next(c for c in result.checks if "description" in c.name.lower())
    assert desc_check.status == "WARN"
    assert "no description" in desc_check.message
    assert "tool_a" in desc_check.message


@pytest.mark.asyncio
async def test_empty_description_produces_warn() -> None:
    client = MagicMock()
    client.list_tools = AsyncMock(
        return_value=[
            _make_tool("tool_a", description=""),
            _make_tool("tool_b", description="Good desc"),
        ]
    )
    call_result = MagicMock()
    call_result.content = [MagicMock(type="text")]
    call_result.isError = False
    client.call_tool = AsyncMock(return_value=call_result)

    suite = ToolsSuite(client)
    result = await suite.run()

    desc_check = next(c for c in result.checks if "description" in c.name.lower())
    assert desc_check.status == "WARN"
    assert "empty description" in desc_check.message
    assert "tool_a" in desc_check.message


@pytest.mark.asyncio
async def test_both_absent_and_empty_description() -> None:
    client = MagicMock()
    client.list_tools = AsyncMock(
        return_value=[
            _make_tool("absent_tool", description=None),
            _make_tool("empty_tool", description=""),
            _make_tool("good_tool", description="Has description"),
        ]
    )
    call_result = MagicMock()
    call_result.content = [MagicMock(type="text")]
    call_result.isError = False
    client.call_tool = AsyncMock(return_value=call_result)

    suite = ToolsSuite(client)
    result = await suite.run()

    desc_check = next(c for c in result.checks if "description" in c.name.lower())
    assert desc_check.status == "WARN"
    assert "no description" in desc_check.message
    assert "absent_tool" in desc_check.message
    assert "empty description" in desc_check.message
    assert "empty_tool" in desc_check.message


@pytest.mark.asyncio
async def test_all_have_descriptions_passes() -> None:
    client = MagicMock()
    client.list_tools = AsyncMock(
        return_value=[
            _make_tool("tool_a", description="Desc A"),
            _make_tool("tool_b", description="Desc B"),
        ]
    )
    call_result = MagicMock()
    call_result.content = [MagicMock(type="text")]
    call_result.isError = False
    client.call_tool = AsyncMock(return_value=call_result)

    suite = ToolsSuite(client)
    result = await suite.run()

    desc_check = next(c for c in result.checks if "description" in c.name.lower())
    assert desc_check.status == "PASS"
