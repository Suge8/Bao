"""Feishu SDK loading and exported symbols."""

from __future__ import annotations

from typing import Any

lark: Any = None
CreateFileRequest: Any = None
CreateFileRequestBody: Any = None
CreateImageRequest: Any = None
CreateImageRequestBody: Any = None
CreateMessageReactionRequest: Any = None
CreateMessageReactionRequestBody: Any = None
CreateMessageRequest: Any = None
CreateMessageRequestBody: Any = None
Emoji: Any = None
GetFileRequest: Any = None
GetMessageResourceRequest: Any = None
PatchMessageRequest: Any = None
PatchMessageRequestBody: Any = None

_feishu_available = False
try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateFileRequest,
        CreateFileRequestBody,
        CreateImageRequest,
        CreateImageRequestBody,
        CreateMessageReactionRequest,
        CreateMessageReactionRequestBody,
        CreateMessageRequest,
        CreateMessageRequestBody,
        Emoji,
        GetFileRequest,
        GetMessageResourceRequest,
        PatchMessageRequest,
        PatchMessageRequestBody,
    )

    _feishu_available = True
except ImportError:
    pass

FEISHU_AVAILABLE = _feishu_available

__all__ = [
    "lark",
    "CreateFileRequest",
    "CreateFileRequestBody",
    "CreateImageRequest",
    "CreateImageRequestBody",
    "CreateMessageReactionRequest",
    "CreateMessageReactionRequestBody",
    "CreateMessageRequest",
    "CreateMessageRequestBody",
    "Emoji",
    "GetFileRequest",
    "GetMessageResourceRequest",
    "PatchMessageRequest",
    "PatchMessageRequestBody",
    "FEISHU_AVAILABLE",
]
