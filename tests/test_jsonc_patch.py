"""Tests for JSONC patch writer."""

from __future__ import annotations

import json
from typing import Any

from app.backend.jsonc_patch import _strip_comments, patch_jsonc

SAMPLE_JSONC = """{
  // Provider config
  "providers": {
    "openai": {
      "apiKey": "old-key",
      "apiBase": null
    }
  },
  /* Agent defaults */
  "agents": {
    "defaults": {
      "model": "gpt-4o",
      "temperature": 0.7
    }
  }
}"""


def _parse(text: str) -> dict[str, Any]:
    return json.loads(_strip_comments(text))


def test_update_existing_string(tmp_path):
    result, errors = patch_jsonc(SAMPLE_JSONC, {"providers.openai.apiKey": "sk-new"})
    assert not errors
    data = _parse(result)
    assert data["providers"]["openai"]["apiKey"] == "sk-new"


def test_update_existing_number():
    result, errors = patch_jsonc(SAMPLE_JSONC, {"agents.defaults.temperature": 0.5})
    assert not errors
    data = _parse(result)
    assert data["agents"]["defaults"]["temperature"] == 0.5


def test_update_null_to_string():
    result, errors = patch_jsonc(
        SAMPLE_JSONC, {"providers.openai.apiBase": "https://api.example.com"}
    )
    assert not errors
    data = _parse(result)
    assert data["providers"]["openai"]["apiBase"] == "https://api.example.com"


def test_keep_comments():
    result, errors = patch_jsonc(SAMPLE_JSONC, {"agents.defaults.model": "claude-3"})
    assert not errors
    assert "// Provider config" in result
    assert "/* Agent defaults */" in result


def test_insert_new_key():
    result, errors = patch_jsonc(SAMPLE_JSONC, {"providers.openai.timeoutMs": 30000})
    assert not errors
    data = _parse(result)
    assert data["providers"]["openai"]["timeoutMs"] == 30000


def test_insert_channel_config():
    base = '{\n  "channels": {}\n}'
    result, errors = patch_jsonc(base, {"channels.telegram": {"enabled": True, "token": "abc"}})
    assert not errors
    data = _parse(result)
    assert data["channels"]["telegram"]["token"] == "abc"


def test_insert_keeps_trailing_comment_with_existing_key():
    base = '{\n  "obj": {\n    "a": 1 // keep\n  }\n}'
    result, errors = patch_jsonc(base, {"obj.b": 2})
    assert not errors
    data = _parse(result)
    assert data["obj"]["a"] == 1
    assert data["obj"]["b"] == 2
    assert result.index("// keep") < result.index('"b"')


def test_multiple_patches():
    result, errors = patch_jsonc(
        SAMPLE_JSONC,
        {
            "providers.openai.apiKey": "sk-multi",
            "agents.defaults.model": "gpt-4-turbo",
        },
    )
    assert not errors
    data = _parse(result)
    assert data["providers"]["openai"]["apiKey"] == "sk-multi"
    assert data["agents"]["defaults"]["model"] == "gpt-4-turbo"


def test_idempotent():
    result1, _ = patch_jsonc(SAMPLE_JSONC, {"providers.openai.apiKey": "sk-idem"})
    result2, _ = patch_jsonc(result1, {"providers.openai.apiKey": "sk-idem"})
    assert _parse(result1) == _parse(result2)


def test_invalid_path_returns_error():
    _, errors = patch_jsonc(SAMPLE_JSONC, {"nonexistent.deep.path": "value"})
    assert errors  # should report error, not crash


def test_result_parseable_after_patch():
    result, errors = patch_jsonc(SAMPLE_JSONC, {"agents.defaults.temperature": 0.9})
    assert not errors
    # Must be parseable after stripping comments
    data = _parse(result)
    assert isinstance(data, dict)


def test_replace_providers_object_with_comments_and_crlf():
    base = (
        "{\r\n"
        "  // provider block\r\n"
        '  "providers": {\r\n'
        '    "openai": {\r\n'
        '      "type": "openai",\r\n'
        '      "apiKey": "old-key"\r\n'
        "    }\r\n"
        "  },\r\n"
        '  "agents": {\r\n'
        '    "defaults": {\r\n'
        '      "model": "openai/gpt-4o"\r\n'
        "    }\r\n"
        "  }\r\n"
        "}\r\n"
    )
    result, errors = patch_jsonc(
        base,
        {
            "providers": {
                "foo.bar": {
                    "type": "openai",
                    "apiKey": "sk-test",
                    "apiBase": "https://api.example.com/v1",
                }
            }
        },
    )

    assert not errors
    data = _parse(result)
    assert data["providers"]["foo.bar"]["apiKey"] == "sk-test"
