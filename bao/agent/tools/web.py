"""Web tools facade: keeps the public tool surface stable."""

from __future__ import annotations

from typing import Any

import httpx

from bao.agent.tools._web_common import (
    BROWSER_BLOCK_MARKERS as _BROWSER_BLOCK_MARKERS,
)
from bao.agent.tools._web_common import (
    BROWSER_BLOCK_STATUSES as _BROWSER_BLOCK_STATUSES,
)
from bao.agent.tools._web_common import (
    FILTER_LEVELS as _FILTER_LEVELS,
)
from bao.agent.tools._web_common import (
    MAX_REDIRECTS,
    USER_AGENT,
)
from bao.agent.tools._web_common import (
    mask_url_credentials as _mask_url_credentials,
)
from bao.agent.tools._web_common import (
    normalize as _normalize,
)
from bao.agent.tools._web_common import (
    safe_error_text as _safe_error_text,
)
from bao.agent.tools._web_common import (
    strip_tags as _strip_tags,
)
from bao.agent.tools._web_common import (
    validate_url as _validate_url,
)
from bao.agent.tools._web_fetch import WebFetchTool
from bao.agent.tools._web_filters import (
    apply_filters as _apply_filters,
)
from bao.agent.tools._web_filters import (
    dedup_adjacent as _dedup_adjacent,
)
from bao.agent.tools._web_filters import (
    filter_boilerplate as _filter_boilerplate,
)
from bao.agent.tools._web_filters import (
    filter_link_heavy as _filter_link_heavy,
)
from bao.agent.tools._web_filters import (
    html_to_markdown as _html_to_markdown,
)
from bao.agent.tools._web_filters import (
    preclean_html as _preclean_html,
)
from bao.agent.tools._web_filters import (
    smart_truncate as _smart_truncate,
)
from bao.agent.tools._web_search import WebSearchTool


def _make_async_client(proxy: str | None, **kwargs: Any) -> httpx.AsyncClient:
    if not proxy:
        return httpx.AsyncClient(**kwargs)
    try:
        return httpx.AsyncClient(proxy=proxy, **kwargs)
    except TypeError:
        fallback_kwargs = dict(kwargs)
        fallback_kwargs["proxies"] = {"http://": proxy, "https://": proxy}
        return httpx.AsyncClient(**fallback_kwargs)


__all__ = [
    "MAX_REDIRECTS",
    "USER_AGENT",
    "WebFetchTool",
    "WebSearchTool",
    "httpx",
    "_BROWSER_BLOCK_MARKERS",
    "_BROWSER_BLOCK_STATUSES",
    "_FILTER_LEVELS",
    "_apply_filters",
    "_dedup_adjacent",
    "_filter_boilerplate",
    "_filter_link_heavy",
    "_html_to_markdown",
    "_make_async_client",
    "_mask_url_credentials",
    "_normalize",
    "_preclean_html",
    "_safe_error_text",
    "_smart_truncate",
    "_strip_tags",
    "_validate_url",
]
