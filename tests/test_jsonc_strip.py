from __future__ import annotations

import json
from typing import Callable, cast

import bao.config.loader as loader

strip_jsonc_comments = cast(Callable[[str], str], getattr(loader, "_strip_jsonc_comments"))


def test_strip_basic_line_comment() -> None:
    text = '{\n  "a": 1, // comment\n  "b": 2\n}'
    assert strip_jsonc_comments(text) == '{\n  "a": 1, \n  "b": 2\n}'


def test_strip_basic_block_comment() -> None:
    text = '{"a": 1, /* block */ "b": 2}'
    assert strip_jsonc_comments(text) == '{"a": 1,  "b": 2}'


def test_preserve_double_slash_in_string() -> None:
    text = '{"note": "this is // not a comment"}'
    assert strip_jsonc_comments(text) == text


def test_preserve_block_markers_in_string() -> None:
    text = '{"note": "/* keep */"}'
    assert strip_jsonc_comments(text) == text


def test_preserve_url_in_string() -> None:
    text = '{"u1": "http://example.com", "u2": "https://example.com/path"}'
    assert strip_jsonc_comments(text) == text


def test_handle_escaped_quote_inside_string() -> None:
    text = r'{"text": "say \"hi\" // still string"} // trailing'
    assert strip_jsonc_comments(text) == r'{"text": "say \"hi\" // still string"} '


def test_mixed_comments_strings_and_urls() -> None:
    text = (
        "{\n"
        "  // top comment\n"
        '  "url": "https://example.com/a//b",\n'
        '  "pattern": "/* keep */",\n'
        '  "x": 1 /* mid block */,\n'
        '  "y": "ok" // end\n'
        "}"
    )
    expected = (
        "{\n"
        "  \n"
        '  "url": "https://example.com/a//b",\n'
        '  "pattern": "/* keep */",\n'
        '  "x": 1 ,\n'
        '  "y": "ok" \n'
        "}"
    )
    assert strip_jsonc_comments(text) == expected


def test_nested_block_comment_boundary() -> None:
    text = '{"a": 1, /* outer /* inner */ tail */ "b": 2}'
    assert strip_jsonc_comments(text) == '{"a": 1,  "b": 2}'


def test_line_comment_without_trailing_newline() -> None:
    text = '{"a": 1}// eof comment'
    assert strip_jsonc_comments(text) == '{"a": 1}'


def test_empty_and_comment_only_inputs() -> None:
    assert strip_jsonc_comments("") == ""
    assert strip_jsonc_comments("// only comment") == ""
    assert strip_jsonc_comments("/* only block */") == ""


def test_real_bao_config_fragment_is_parseable() -> None:
    snippet = """{
  // provider example from bao config template
  "providers": {
    "openai": {
      "type": "openai",
      "apiBase": "https://api.openai.com/v1",
      "note": "url http://localhost:11434 should stay"
    }
  },
  /* runtime config */
  "agents": {
    "defaults": {
      "model": "openai/gpt-5.2"
    }
  }
}"""
    stripped = strip_jsonc_comments(snippet)
    data = cast(dict[str, object], json.loads(stripped))
    providers = cast(dict[str, object], data["providers"])
    openai = cast(dict[str, object], providers["openai"])
    agents = cast(dict[str, object], data["agents"])
    defaults = cast(dict[str, object], agents["defaults"])

    assert openai["apiBase"] == "https://api.openai.com/v1"
    assert cast(str, openai["note"]).endswith("should stay")
    assert defaults["model"] == "openai/gpt-5.2"
