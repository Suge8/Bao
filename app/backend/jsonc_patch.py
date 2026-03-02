"""JSONC round-trip patch writer.

Parses JSONC (JSON with // and /* */ comments), records byte spans for each
value, then applies targeted replacements without touching comments or
unrelated content.

Algorithm:
  1. Tokenize: produce tokens (STRING, NUMBER, BOOL, NULL, LBRACE, RBRACE,
     LBRACKET, RBRACKET, COLON, COMMA, COMMENT, WHITESPACE)
  2. Parse: recursive descent, recording (value_start, value_end) byte offsets
     for every object property value, and the offset of every closing '}'.
  3. Patch: for each (path, new_value) pair, locate the span and replace only
     that fragment. Apply patches right-to-left to avoid offset drift.
  4. Validate: strip comments + json.loads on result.

Limitations (by design):
  - Does not uncomment commented-out blocks.
  - Does not reorder keys.
  - On parse failure for a given path, returns a structured error.

Deletion:
  Pass value = _DELETE_SENTINEL for a dotpath to remove that key entirely.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import cast

# Sentinel value for key deletion
_DELETE_SENTINEL = object()


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<COMMENT_LINE>//[^\n]*)
    |(?P<COMMENT_BLOCK>/\*.*?\*/)
    |(?P<STRING>"(?:[^"\\]|\\.)*")
    |(?P<NUMBER>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)
    |(?P<BOOL>true|false)
    |(?P<NULL>null)
    |(?P<LBRACE>\{)
    |(?P<RBRACE>\})
    |(?P<LBRACKET>\[)
    |(?P<RBRACKET>\])
    |(?P<COLON>:)
    |(?P<COMMA>,)
    |(?P<WS>\s+)
    """,
    re.VERBOSE | re.DOTALL,
)


@dataclass
class Token:
    kind: str
    value: str
    start: int
    end: int


def _tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise ValueError(f"Unexpected character at offset {pos}: {text[pos]!r}")
        kind = m.lastgroup
        assert kind is not None
        tokens.append(Token(kind, m.group(), m.start(), m.end()))
        pos = m.end()
    return tokens


# ---------------------------------------------------------------------------
# Parser — builds a span tree
# ---------------------------------------------------------------------------


@dataclass
class _Span:
    """Records the byte span of a JSON value."""

    start: int
    end: int


@dataclass
class _ObjNode:
    """Parsed object: maps key -> child value span/node, plus closing brace offset."""

    children: dict[str, "_ObjNode | _Span"] = field(default_factory=dict)
    close_brace: int = -1  # offset of '}'
    open_brace: int = -1  # offset of '{'
    # offset just before '}' where we can insert new keys
    insert_before: int = -1


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens: list[Token] = [
            token for token in tokens if token.kind not in ("WS", "COMMENT_LINE", "COMMENT_BLOCK")
        ]
        self._pos: int = 0

    def _peek(self) -> Token | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self, kind: str | None = None) -> Token:
        t = self._tokens[self._pos]
        if kind and t.kind != kind:
            raise ValueError(f"Expected {kind}, got {t.kind} at offset {t.start}")
        self._pos += 1
        return t

    def parse_value(self) -> "_ObjNode | _Span":
        t = self._peek()
        if t is None:
            raise ValueError("Unexpected end of input")
        if t.kind == "LBRACE":
            return self._parse_object()
        if t.kind == "LBRACKET":
            return self._parse_array()
        # Scalar
        self._pos += 1
        return _Span(t.start, t.end)

    def _parse_object(self) -> _ObjNode:
        open_tok = self._consume("LBRACE")
        node = _ObjNode()
        node.open_brace = open_tok.start

        while True:
            t = self._peek()
            if t is None:
                raise ValueError("Unterminated object")
            if t.kind == "RBRACE":
                node.insert_before = t.start
                node.close_brace = t.start
                _ = self._consume("RBRACE")
                return node
            if t.kind == "COMMA":
                _ = self._consume("COMMA")
                continue
            # key
            key_tok = self._consume("STRING")
            key = cast(str, json.loads(key_tok.value))
            _ = self._consume("COLON")
            child = self.parse_value()
            node.children[key] = child

    def _parse_array(self) -> _Span:
        start = self._peek()
        assert start is not None
        depth = 0
        begin = start.start
        end = start.end
        while True:
            t = self._peek()
            if t is None:
                raise ValueError("Unterminated array")
            if t.kind == "LBRACKET":
                depth += 1
            elif t.kind == "RBRACKET":
                depth -= 1
                end = t.end
                self._pos += 1
                if depth == 0:
                    return _Span(begin, end)
                continue
            end = t.end
            self._pos += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class PatchError:
    path: list[str]
    message: str


def patch_jsonc(
    text: str,
    changes: dict[str, object],
) -> tuple[str, list[PatchError]]:
    """Apply *changes* to *text* (JSONC), returning (patched_text, errors).

    *changes* is a flat dict mapping dot-separated paths to new values.
    Example: {"providers.openai.apiKey": "sk-xxx", "agents.defaults.model": "gpt-4o"}

    For nested paths that don't exist yet, the function will attempt to insert
    into the nearest existing ancestor object.
    """
    tokens = _tokenize(text)
    parser = _Parser(tokens)
    try:
        root = parser.parse_value()
    except ValueError as e:
        return text, [PatchError([], f"Parse error: {e}")]

    if not isinstance(root, _ObjNode):
        return text, [PatchError([], "Root is not a JSON object")]

    patches: list[tuple[int, int, str]] = []  # (start, end, replacement)
    errors: list[PatchError] = []

    for dotpath, new_value in changes.items():
        path = dotpath.split(".")
        err = _collect_patch(root, path, new_value, text, patches)
        if err:
            errors.append(PatchError(path, err))

    if not patches:
        return text, errors

    # Apply right-to-left to avoid offset drift
    patches.sort(key=lambda p: p[0], reverse=True)
    result = text
    for start, end, replacement in patches:
        result = result[:start] + replacement + result[end:]

    # Validate
    try:
        stripped = _strip_comments(result)
        json.loads(stripped)
    except (json.JSONDecodeError, ValueError) as e:
        return text, errors + [PatchError([], f"Post-patch validation failed: {e}")]

    return result, errors


def _collect_patch(
    node: "_ObjNode | _Span",
    path: list[str],
    value: object,
    text: str,
    patches: list[tuple[int, int, str]],
) -> str | None:
    """Recursively walk *path* in *node*, collecting a patch. Returns error string or None."""
    if not path:
        return "Empty path"

    if not isinstance(node, _ObjNode):
        return f"Cannot descend into scalar at remaining path {path}"

    key = path[0]
    rest = path[1:]

    if key in node.children:
        child = node.children[key]
        if rest:
            return _collect_patch(child, rest, value, text, patches)
        # Replace this value's span
        if isinstance(child, _Span):
            replacement = json.dumps(value, ensure_ascii=False)
            patches.append((child.start, child.end, replacement))
            return None
        else:
            # Replace entire object value
            close = child.close_brace + 1
            open_pos = child.open_brace
            if open_pos == -1:
                return f"Cannot locate open brace for object at key {key!r}"
            replacement = json.dumps(value, ensure_ascii=False, indent=2)
            patches.append((open_pos, close, replacement))
            return None
    else:
        # Key doesn't exist — insert into this object
        if rest:
            return f"Intermediate key {key!r} not found; cannot create nested path"
        # Build insertion: find insert_before position
        insert_pos = node.insert_before
        if insert_pos == -1:
            return f"Cannot determine insertion point for key {key!r}"

        # Determine indentation: find the line containing close_brace, take leading whitespace only
        line_start = text.rfind("\n", 0, node.close_brace)
        if line_start != -1:
            line_content = text[line_start + 1 : node.close_brace]
            brace_indent = ""
            for ch in line_content:
                if ch in (" ", "\t"):
                    brace_indent += ch
                else:
                    break
        else:
            brace_indent = ""
        value_indent = brace_indent + "  "

        # Need a leading comma if there's existing content
        needs_comma = bool(node.children)
        new_entry = (
            (",\n" if needs_comma else "\n")
            + value_indent
            + json.dumps(key, ensure_ascii=False)
            + ": "
            + json.dumps(value, ensure_ascii=False)
        )
        patches.append((insert_pos, insert_pos, new_entry))
        return None


def _strip_comments(text: str) -> str:
    """Remove // and /* */ comments, preserving string contents."""
    tokens = _tokenize(text)
    parts: list[str] = []
    for t in tokens:
        if t.kind in ("COMMENT_LINE", "COMMENT_BLOCK"):
            # Replace with whitespace to preserve offsets for error messages
            parts.append(" " * len(t.value))
        else:
            parts.append(t.value)
    return "".join(parts)


def strip_comments(text: str) -> str:
    return _strip_comments(text)
