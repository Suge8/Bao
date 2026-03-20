"""Feishu message formatting helpers."""

from __future__ import annotations

import re
from typing import Any, Literal

FeishuMessageFormat = Literal["text", "post", "interactive"]


class _FeishuFormatMixin:
    _TABLE_RE = re.compile(
        r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
        re.MULTILINE,
    )
    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    _CODE_BLOCK_RE = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)
    _LIST_RE = re.compile(r"^[ \t]*[-*+]\s+", re.MULTILINE)
    _OLIST_RE = re.compile(r"^[ \t]*\d+\.\s+", re.MULTILINE)
    _MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    _COMPLEX_MD_RE = re.compile(r"(\*\*.+?\*\*)|(__.+?__)|(`[^`\n]+`)|(^>\s+)", re.MULTILINE)
    _TEXT_MAX_LEN = 200
    _POST_MAX_LEN = 2000

    @staticmethod
    def _parse_md_table(table_text: str) -> dict[str, Any] | None:
        lines = [line.strip() for line in table_text.strip().split("\n") if line.strip()]
        if len(lines) < 3:
            return None

        def split_row(row: str) -> list[str]:
            return [cell.strip() for cell in row.strip("|").split("|")]

        headers = split_row(lines[0])
        rows = [split_row(row) for row in lines[2:]]
        columns = [
            {"tag": "column", "name": f"c{index}", "display_name": header, "width": "auto"}
            for index, header in enumerate(headers)
        ]
        return {
            "tag": "table",
            "page_size": len(rows) + 1,
            "columns": columns,
            "rows": [
                {f"c{index}": row[index] if index < len(row) else "" for index in range(len(headers))}
                for row in rows
            ],
        }

    def _build_card_elements(self, content: str) -> list[dict[str, Any]]:
        elements: list[dict[str, Any]] = []
        last_end = 0
        for match in self._TABLE_RE.finditer(content):
            before = content[last_end : match.start()]
            if before.strip():
                elements.extend(self._split_headings(before))
            elements.append(
                self._parse_md_table(match.group(1))
                or {"tag": "markdown", "content": match.group(1)}
            )
            last_end = match.end()
        remaining = content[last_end:]
        if remaining.strip():
            elements.extend(self._split_headings(remaining))
        return elements or [{"tag": "markdown", "content": content}]

    @staticmethod
    def _split_elements_by_table_limit(
        elements: list[dict[str, Any]],
        max_tables: int = 1,
    ) -> list[list[dict[str, Any]]]:
        if not elements:
            return [[]]

        groups: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        table_count = 0
        for element in elements:
            if element.get("tag") == "table":
                if table_count >= max_tables and current:
                    groups.append(current)
                    current = []
                    table_count = 0
                current.append(element)
                table_count += 1
                continue
            current.append(element)
        if current:
            groups.append(current)
        return groups or [[]]

    def _split_headings(self, content: str) -> list[dict[str, Any]]:
        protected = content
        code_blocks: list[str] = []
        for match in self._CODE_BLOCK_RE.finditer(content):
            code_blocks.append(match.group(1))
            protected = protected.replace(match.group(1), f"\x00CODE{len(code_blocks) - 1}\x00", 1)

        elements: list[dict[str, Any]] = []
        last_end = 0
        for match in self._HEADING_RE.finditer(protected):
            before = protected[last_end : match.start()].strip()
            if before:
                elements.append({"tag": "markdown", "content": before})
            text = match.group(2).strip()
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{text}**"}})
            last_end = match.end()
        remaining = protected[last_end:].strip()
        if remaining:
            elements.append({"tag": "markdown", "content": remaining})

        for index, code_block in enumerate(code_blocks):
            for element in elements:
                if element.get("tag") == "markdown":
                    element["content"] = element["content"].replace(f"\x00CODE{index}\x00", code_block)

        return elements or [{"tag": "markdown", "content": content}]

    def _has_interactive_content(self, text: str) -> bool:
        return bool(
            self._TABLE_RE.search(text)
            or self._HEADING_RE.search(text)
            or self._CODE_BLOCK_RE.search(text)
            or self._LIST_RE.search(text)
            or self._OLIST_RE.search(text)
            or self._COMPLEX_MD_RE.search(text)
        )

    def _detect_msg_format(self, content: str) -> FeishuMessageFormat:
        text = content.strip()
        if not text:
            return "text"
        if self._has_interactive_content(text):
            return "interactive"
        if len(text) <= self._TEXT_MAX_LEN and not self._MD_LINK_RE.search(text):
            return "text"
        if len(text) <= self._POST_MAX_LEN:
            return "post"
        return "interactive"

    @classmethod
    def _markdown_to_post(cls, content: str) -> dict[str, Any]:
        paragraphs: list[list[dict[str, str]]] = []

        for raw_line in content.strip().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            block: list[dict[str, str]] = []
            cursor = 0
            for match in cls._MD_LINK_RE.finditer(line):
                start, end = match.span()
                if start > cursor:
                    block.append({"tag": "text", "text": line[cursor:start]})
                block.append({"tag": "a", "text": match.group(1), "href": match.group(2)})
                cursor = end
            if cursor < len(line):
                block.append({"tag": "text", "text": line[cursor:]})
            if block:
                paragraphs.append(block)

        fallback = [[{"tag": "text", "text": content}]]
        return {"zh_cn": {"title": "", "content": paragraphs or fallback}}
