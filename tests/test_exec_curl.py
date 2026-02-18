r"""Tests for ExecTool safety guard — format pattern false positive.

The old deny pattern `\b(format|mkfs|diskpart)\b` matched "format" inside
URLs (e.g. `curl https://wttr.in?format=3`) because `?` is a non-word
character, so `\b` fires between `?` and `f`.

The fix splits the pattern:
  - `(?:^|[;&|]\s*)format\b`  — only matches `format` as a standalone command
  - `\b(mkfs|diskpart)\b`     — kept as-is (unique enough to not false-positive)
"""

import re

import pytest

from nanobot.agent.tools.shell import ExecTool


# --- Guard regression: "format" in URLs must not be blocked ---


@pytest.mark.asyncio
async def test_curl_with_format_in_url_not_blocked():
    """curl with ?format= in URL should NOT be blocked by the guard."""
    tool = ExecTool(working_dir="/tmp")
    result = await tool.execute(
        command="curl -s 'https://wttr.in/Brooklyn?format=3'"
    )
    assert "blocked by safety guard" not in result


@pytest.mark.asyncio
async def test_curl_with_format_in_post_body_not_blocked():
    """curl with 'format=json' in POST body should NOT be blocked."""
    tool = ExecTool(working_dir="/tmp")
    result = await tool.execute(
        command="curl -s -d 'format=json' https://httpbin.org/post"
    )
    assert "blocked by safety guard" not in result


@pytest.mark.asyncio
async def test_curl_without_format_not_blocked():
    """Plain curl commands should pass the guard."""
    tool = ExecTool(working_dir="/tmp")
    result = await tool.execute(command="curl -s https://httpbin.org/get")
    assert "blocked by safety guard" not in result


# --- The guard still blocks actual format commands ---


@pytest.mark.asyncio
async def test_guard_blocks_standalone_format_command():
    """'format c:' as a standalone command must be blocked."""
    tool = ExecTool(working_dir="/tmp")
    result = await tool.execute(command="format c:")
    assert "blocked by safety guard" in result


@pytest.mark.asyncio
async def test_guard_blocks_format_after_semicolon():
    """'echo hi; format c:' must be blocked."""
    tool = ExecTool(working_dir="/tmp")
    result = await tool.execute(command="echo hi; format c:")
    assert "blocked by safety guard" in result


@pytest.mark.asyncio
async def test_guard_blocks_format_after_pipe():
    """'echo hi | format' must be blocked."""
    tool = ExecTool(working_dir="/tmp")
    result = await tool.execute(command="echo hi | format")
    assert "blocked by safety guard" in result


# --- Regex unit tests (no I/O) ---


def test_format_pattern_blocks_disk_commands():
    """The tightened pattern still catches actual format commands."""
    pattern = r"(?:^|[;&|]\s*)format\b"

    assert re.search(pattern, "format c:")
    assert re.search(pattern, "echo hi; format c:")
    assert re.search(pattern, "echo hi | format")
    assert re.search(pattern, "cmd && format d:")


def test_format_pattern_allows_urls_and_flags():
    """The tightened pattern does NOT match format inside URLs or flags."""
    pattern = r"(?:^|[;&|]\s*)format\b"

    assert not re.search(pattern, "curl https://wttr.in?format=3")
    assert not re.search(pattern, "echo --output-format=json")
    assert not re.search(pattern, "curl -d 'format=json' https://api.example.com")
    assert not re.search(pattern, "python -c 'print(\"{:format}\".format(1))'")
