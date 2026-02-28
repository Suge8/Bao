from bao.agent import shared

_ERROR_KEYWORDS = ("error:", "traceback", "failed", "exception", "permission denied")


def test_web_search_ignores_content_keywords() -> None:
    assert not shared.has_tool_error(
        "web_search",
        "Results for: query\n[1] Debugging failed requests\n   https://example.com",
        _ERROR_KEYWORDS,
    )


def test_web_search_detects_explicit_error_prefix() -> None:
    assert shared.has_tool_error("web_search", "Error: upstream timeout", _ERROR_KEYWORDS)


def test_web_fetch_detects_json_error_payload() -> None:
    assert shared.has_tool_error(
        "web_fetch",
        '{"error": "URL validation failed: Missing domain"}',
        _ERROR_KEYWORDS,
    )


def test_web_fetch_detects_indented_json_error_payload() -> None:
    assert shared.has_tool_error(
        "web_fetch",
        '\n  {"error": "network unreachable"}',
        _ERROR_KEYWORDS,
    )


def test_web_fetch_detects_malformed_json_with_error_marker() -> None:
    assert shared.has_tool_error(
        "web_fetch",
        '{"error": "network unreachable"',
        _ERROR_KEYWORDS,
    )


def test_web_fetch_does_not_false_positive_on_embedded_error_text() -> None:
    assert not shared.has_tool_error(
        "web_fetch",
        '{"url": "https://example.com", "text": "example with \\"error\\": value"}',
        _ERROR_KEYWORDS,
    )


def test_web_tools_detect_error_executing_prefix() -> None:
    assert shared.has_tool_error(
        "web_search", "Error executing web_search: provider crashed", _ERROR_KEYWORDS
    )
    assert shared.has_tool_error(
        "web_fetch", "Error executing web_fetch: readability missing", _ERROR_KEYWORDS
    )


def test_other_tools_keep_keyword_based_detection() -> None:
    assert shared.has_tool_error("exec", "command failed with exit code 1", _ERROR_KEYWORDS)


def test_exec_detects_nonzero_exit_code_marker() -> None:
    text = "stdout...\nExit code: 2\n"
    assert shared.has_tool_error("exec", text, _ERROR_KEYWORDS)


def test_exec_zero_exit_code_not_error_without_keywords() -> None:
    text = "all done\nExit code: 0\n"
    assert not shared.has_tool_error("exec", text, _ERROR_KEYWORDS)


def test_coding_agent_detects_error_json_status() -> None:
    payload = '{"status":"error","summary":"failed to run"}'
    assert shared.has_tool_error("coding_agent", payload, _ERROR_KEYWORDS)


def test_coding_agent_detects_nonzero_exit_code_json() -> None:
    payload = '{"status":"ok","exit_code":1}'
    assert shared.has_tool_error("coding_agent", payload, _ERROR_KEYWORDS)


def test_coding_agent_detects_prefixed_json_error_payload() -> None:
    payload = 'result summary: {"status":"error","summary":"boom"}'
    assert shared.has_tool_error("coding_agent", payload, _ERROR_KEYWORDS)


def test_coding_agent_detects_camel_case_exit_code() -> None:
    payload = '{"status":"ok","exitCode":1}'
    assert shared.has_tool_error("coding_agent", payload, _ERROR_KEYWORDS)
