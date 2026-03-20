from __future__ import annotations

from bao.utils.db import get_db, open_or_create_table

from ._manager_base import SessionManagerBase
from ._manager_control import SessionManagerControlMixin
from ._manager_display import SessionManagerDisplayMixin
from ._manager_models import (
    _DISPLAY_TAIL_CACHE_LIMIT,
    _DISPLAY_TAIL_SESSION_CACHE_LIMIT,
    _RUNTIME_CONTEXT_TAG,
    DisplayTailSnapshot as _DisplayTailSnapshot,
    MarkDesktopSeenRequest,
    escape_sql_value as _escape,
    Session,
    SessionChangeEvent,
    synchronized as _synchronized,
)
from ._manager_persistence import SessionManagerPersistenceMixin
from ._manager_save import SessionManagerSaveMixin
from ._manager_tables import SessionManagerTablesMixin


class SessionManager(
    SessionManagerTablesMixin,
    SessionManagerBase,
    SessionManagerDisplayMixin,
    SessionManagerSaveMixin,
    SessionManagerPersistenceMixin,
    SessionManagerControlMixin,
):
    pass


__all__ = [
    "_DISPLAY_TAIL_CACHE_LIMIT",
    "_DISPLAY_TAIL_SESSION_CACHE_LIMIT",
    "_DisplayTailSnapshot",
    "_escape",
    "_RUNTIME_CONTEXT_TAG",
    "_synchronized",
    "MarkDesktopSeenRequest",
    "Session",
    "SessionChangeEvent",
    "SessionManager",
    "get_db",
    "open_or_create_table",
]
