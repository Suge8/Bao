"""Token storage helpers."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from nanobot.auth.codex.constants import TOKEN_FILENAME
from nanobot.auth.codex.models import CodexToken
from nanobot.utils.helpers import ensure_dir, get_data_path


def _get_token_path() -> Path:
    auth_dir = ensure_dir(get_data_path() / "auth")
    return auth_dir / TOKEN_FILENAME


def _load_token_file() -> CodexToken | None:
    path = _get_token_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return CodexToken(
            access=data["access"],
            refresh=data["refresh"],
            expires=int(data["expires"]),
            account_id=data["account_id"],
        )
    except Exception:
        return None


def _save_token_file(token: CodexToken) -> None:
    path = _get_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "access": token.access,
                "refresh": token.refresh,
                "expires": token.expires,
                "account_id": token.account_id,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except Exception:
        # Ignore permission setting failures.
        pass


def _try_import_codex_cli_token() -> CodexToken | None:
    codex_path = Path.home() / ".codex" / "auth.json"
    if not codex_path.exists():
        return None
    try:
        data = json.loads(codex_path.read_text(encoding="utf-8"))
        tokens = data.get("tokens") or {}
        access = tokens.get("access_token")
        refresh = tokens.get("refresh_token")
        account_id = tokens.get("account_id")
        if not access or not refresh or not account_id:
            return None
        try:
            mtime = codex_path.stat().st_mtime
            expires = int(mtime * 1000 + 60 * 60 * 1000)
        except Exception:
            expires = int(time.time() * 1000 + 60 * 60 * 1000)
        token = CodexToken(
            access=str(access),
            refresh=str(refresh),
            expires=expires,
            account_id=str(account_id),
        )
        _save_token_file(token)
        return token
    except Exception:
        return None


class _FileLock:
    """Simple file lock to reduce concurrent refreshes."""

    def __init__(self, path: Path):
        self._path = path
        self._fp = None

    def __enter__(self) -> "_FileLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self._path, "a+")
        try:
            import fcntl

            fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX)
        except Exception:
            # Non-POSIX or failed lock: continue without locking.
            pass
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            import fcntl

            fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            if self._fp:
                self._fp.close()
        except Exception:
            pass
