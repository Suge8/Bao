from __future__ import annotations

from tests._tool_validation_testkit import SampleTool


def test_validate_params_missing_required() -> None:
    assert "missing required count" in "; ".join(SampleTool().validate_params({"query": "hi"}))


def test_validate_params_type_and_range() -> None:
    tool = SampleTool()
    assert any("count must be >= 1" in error for error in tool.validate_params({"query": "hi", "count": 0}))
    assert any("count should be integer" in error for error in tool.validate_params({"query": "hi", "count": "2"}))


def test_validate_params_enum_and_min_length() -> None:
    errors = SampleTool().validate_params({"query": "h", "count": 2, "mode": "slow"})
    assert any("query must be at least 2 chars" in error for error in errors)
    assert any("mode must be one of" in error for error in errors)


def test_validate_params_nested_object_and_array() -> None:
    errors = SampleTool().validate_params({"query": "hi", "count": 2, "meta": {"flags": [1, "ok"]}})
    assert any("missing required meta.tag" in error for error in errors)
    assert any("meta.flags[0] should be string" in error for error in errors)


def test_validate_params_ignores_unknown_fields() -> None:
    assert SampleTool().validate_params({"query": "hi", "count": 2, "extra": "x"}) == []
