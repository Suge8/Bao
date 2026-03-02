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


def test_coding_agent_details_same_as_coding_agent() -> None:
    """coding_agent_details uses the same detection logic as coding_agent."""
    payload = '{"status":"error","summary":"failed to run"}'
    assert shared.has_tool_error("coding_agent_details", payload, _ERROR_KEYWORDS)
    payload_ok = '{"status":"ok","exit_code":0}'
    assert not shared.has_tool_error("coding_agent_details", payload_ok, _ERROR_KEYWORDS)


def test_coding_agent_detects_timed_out_true() -> None:
    payload = '{"status":"ok","timed_out":true}'
    assert shared.has_tool_error("coding_agent", payload, _ERROR_KEYWORDS)


def test_coding_agent_detects_timedout_camel() -> None:
    payload = '{"timedOut":true}'
    assert shared.has_tool_error("coding_agent", payload, _ERROR_KEYWORDS)


def test_coding_agent_detects_returncode_nonzero() -> None:
    payload = '{"returncode":1}'
    assert shared.has_tool_error("coding_agent", payload, _ERROR_KEYWORDS)


def test_tool_trace_contains_ok_and_error_substrings() -> None:
    ok_entry = shared.build_tool_trace_entry(1, "exec", "cmd", False, "ok result")
    assert "\u2192 ok" in ok_entry
    err_entry = shared.build_tool_trace_entry(2, "exec", "cmd", True, "err")
    assert "\u2192 ERROR" in err_entry


def test_interrupted_not_error() -> None:
    from bao.agent.shared import parse_tool_error

    info = parse_tool_error("exec", "Cancelled by soft interrupt.", _ERROR_KEYWORDS)
    assert info is not None
    assert info.is_error is False
    assert info.category == "interrupted"
    # has_tool_error must return False for interrupted
    assert not shared.has_tool_error("exec", "Cancelled by soft interrupt.", _ERROR_KEYWORDS)


def test_parse_tool_error_invalid_params() -> None:
    from bao.agent.shared import parse_tool_error

    info = parse_tool_error(
        "my_tool",
        "Error: Invalid parameters for tool 'my_tool': missing x",
        _ERROR_KEYWORDS,
    )
    assert info is not None
    assert info.is_error is True
    assert info.category == "invalid_params"
