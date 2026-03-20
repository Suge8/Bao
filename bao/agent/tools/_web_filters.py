from __future__ import annotations

import re

from bao.agent.tools._web_common import normalize, strip_tags

PRECLEAN_RE = re.compile(
    r"<(?:script|style|noscript|iframe|svg)[\s>][\s\S]*?</(?:script|style|noscript|iframe|svg)>",
    re.I,
)
BOILERPLATE_RE = re.compile(
    r"^\s*("
    r"accept\s+(all\s+)?cookies"
    r"|cookie\s+(settings|preferences|policy)"
    r"|share\s+(on|via|to)\s"
    r"|follow\s+us\b"
    r"|subscribe\s+(to|now|for)"
    r"|sign\s+up\s+(for|now|free)"
    r"|copyright\s*[©(]"
    r"|all\s+rights\s+reserved"
    r"|terms\s+(of\s+)?(use|service)"
    r"|privacy\s+policy"
    r"|cookie\s+policy"
    r"|powered\s+by\b"
    r"|advertisement"
    r"|loading\.{2,}"
    r"|please\s+wait"
    r").*$",
    re.I,
)
LINK_RE = re.compile(r"\[.*?\]\(.*?\)")
REF_HEADING_RE = re.compile(
    r"(references?|links?|resources?|参考|资源|相关链接|see also)",
    re.I,
)
SENTENCE_END_RE = re.compile(r"[.!?。！？]\s")
BOILERPLATE_MAX_LINE_LEN = 100
BOILERPLATE_WINDOW = 500
TRUNCATED_SUFFIX = "\n\n[... truncated]"


def preclean_html(raw_html: str) -> str:
    return PRECLEAN_RE.sub("", raw_html)


def is_boilerplate_line(line: str) -> bool:
    stripped = line.strip()
    return 0 < len(stripped) <= BOILERPLATE_MAX_LINE_LEN and BOILERPLATE_RE.search(stripped) is not None


def filter_boilerplate(text: str) -> str:
    if len(text) < BOILERPLATE_WINDOW * 2:
        return "\n".join(line for line in text.split("\n") if not is_boilerplate_line(line))

    head_end = text.find("\n", BOILERPLATE_WINDOW)
    if head_end == -1:
        head_end = BOILERPLATE_WINDOW
    tail_start = text.rfind("\n", 0, len(text) - BOILERPLATE_WINDOW)
    if tail_start == -1:
        tail_start = len(text) - BOILERPLATE_WINDOW

    head_lines = [line for line in text[:head_end].split("\n") if not is_boilerplate_line(line)]
    tail_lines = [line for line in text[tail_start:].split("\n") if not is_boilerplate_line(line)]
    return "\n".join(head_lines) + text[head_end:tail_start] + "\n".join(tail_lines)


def dedup_adjacent(text: str) -> str:
    paragraphs = text.split("\n\n")
    if len(paragraphs) <= 1:
        return text
    result = [paragraphs[0]]
    for para in paragraphs[1:]:
        if para.strip().lower() != result[-1].strip().lower():
            result.append(para)
    return "\n\n".join(result)


def is_link_heavy(para: str) -> bool:
    stripped = para.strip()
    if not stripped:
        return False
    links = LINK_RE.findall(stripped)
    if len(links) < 3:
        return False
    return sum(len(match) for match in links) / len(stripped) >= 0.8


def filter_link_heavy(text: str) -> str:
    paragraphs = text.split("\n\n")
    result: list[str] = []
    for index, para in enumerate(paragraphs):
        if is_link_heavy(para) and not (index > 0 and REF_HEADING_RE.search(paragraphs[index - 1])):
            continue
        result.append(para)
    return "\n\n".join(result)


def smart_truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False

    floor = int(max_chars * 0.85)
    cut = text.rfind("\n\n", floor, max_chars)
    if cut != -1:
        return text[:cut].rstrip() + TRUNCATED_SUFFIX, True

    cut = text.rfind("\n", floor, max_chars)
    if cut != -1:
        return text[:cut].rstrip() + TRUNCATED_SUFFIX, True

    matches = list(SENTENCE_END_RE.finditer(text[floor:max_chars]))
    if matches:
        return text[: floor + matches[-1].end()].rstrip() + TRUNCATED_SUFFIX, True

    return text[:max_chars] + TRUNCATED_SUFFIX, True


def apply_filters(text: str, level: str) -> tuple[str, bool]:
    if level == "none":
        return text, False

    original = text
    text = normalize(dedup_adjacent(filter_boilerplate(text)))
    if level == "aggressive":
        text = normalize(filter_link_heavy(text))
    return text, text != original


def html_to_markdown(html_content: str) -> str:
    text = re.sub(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
        lambda match: f"[{strip_tags(match[2])}]({match[1]})",
        html_content,
        flags=re.I,
    )
    text = re.sub(
        r"<h([1-6])[^>]*>([\s\S]*?)</h\1>",
        lambda match: f"\n{'#' * int(match[1])} {strip_tags(match[2])}\n",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"<li[^>]*>([\s\S]*?)</li>",
        lambda match: f"\n- {strip_tags(match[1])}",
        text,
        flags=re.I,
    )
    text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
    return normalize(strip_tags(text))
