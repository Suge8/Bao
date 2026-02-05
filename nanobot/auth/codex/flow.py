"""Codex OAuth login and token management."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import urllib.parse
import webbrowser
from typing import Any, Callable

import httpx

from nanobot.auth.codex.constants import (
    AUTHORIZE_URL,
    CLIENT_ID,
    DEFAULT_ORIGINATOR,
    MANUAL_PROMPT_DELAY_SEC,
    REDIRECT_URI,
    SCOPE,
    TOKEN_URL,
)
from nanobot.auth.codex.models import CodexToken
from nanobot.auth.codex.pkce import (
    _create_state,
    _decode_account_id,
    _generate_pkce,
    _parse_authorization_input,
    _parse_token_payload,
)
from nanobot.auth.codex.server import _start_local_server
from nanobot.auth.codex.storage import (
    _FileLock,
    _get_token_path,
    _load_token_file,
    _save_token_file,
    _try_import_codex_cli_token,
)


def _exchange_code_for_token(code: str, verifier: str) -> CodexToken:
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": REDIRECT_URI,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if response.status_code != 200:
        raise RuntimeError(f"Token exchange failed: {response.status_code} {response.text}")

    payload = response.json()
    access, refresh, expires_in = _parse_token_payload(payload, "Token response missing fields")
    print("Received access token:", access)
    account_id = _decode_account_id(access)
    return CodexToken(
        access=access,
        refresh=refresh,
        expires=int(time.time() * 1000 + expires_in * 1000),
        account_id=account_id,
    )


async def _exchange_code_for_token_async(code: str, verifier: str) -> CodexToken:
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": REDIRECT_URI,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code != 200:
        raise RuntimeError(f"Token exchange failed: {response.status_code} {response.text}")

    payload = response.json()
    access, refresh, expires_in = _parse_token_payload(payload, "Token response missing fields")

    account_id = _decode_account_id(access)
    return CodexToken(
        access=access,
        refresh=refresh,
        expires=int(time.time() * 1000 + expires_in * 1000),
        account_id=account_id,
    )


def _refresh_token(refresh_token: str) -> CodexToken:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if response.status_code != 200:
        raise RuntimeError(f"Token refresh failed: {response.status_code} {response.text}")

    payload = response.json()
    access, refresh, expires_in = _parse_token_payload(payload, "Token refresh response missing fields")

    account_id = _decode_account_id(access)
    return CodexToken(
        access=access,
        refresh=refresh,
        expires=int(time.time() * 1000 + expires_in * 1000),
        account_id=account_id,
    )


def get_codex_token() -> CodexToken:
    """Get an available token (refresh if needed)."""
    token = _load_token_file() or _try_import_codex_cli_token()
    if not token:
        raise RuntimeError("Codex OAuth credentials not found. Please run the login command.")

    # Refresh 60 seconds early.
    now_ms = int(time.time() * 1000)
    if token.expires - now_ms > 60 * 1000:
        return token

    lock_path = _get_token_path().with_suffix(".lock")
    with _FileLock(lock_path):
        # Re-read to avoid stale token if another process refreshed it.
        token = _load_token_file() or token
        now_ms = int(time.time() * 1000)
        if token.expires - now_ms > 60 * 1000:
            return token
        try:
            refreshed = _refresh_token(token.refresh)
            _save_token_file(refreshed)
            return refreshed
        except Exception:
            # If refresh fails, re-read the file to avoid false negatives.
            latest = _load_token_file()
            if latest and latest.expires - now_ms > 0:
                return latest
            raise


def ensure_codex_token_available() -> None:
    """Ensure a valid token is available; raise if not."""
    _ = get_codex_token()


async def _read_stdin_line() -> str:
    loop = asyncio.get_running_loop()
    if hasattr(loop, "add_reader") and sys.stdin:
        future: asyncio.Future[str] = loop.create_future()

        def _on_readable() -> None:
            line = sys.stdin.readline()
            if not future.done():
                future.set_result(line)

        try:
            loop.add_reader(sys.stdin, _on_readable)
        except Exception:
            return await loop.run_in_executor(None, sys.stdin.readline)

        try:
            return await future
        finally:
            try:
                loop.remove_reader(sys.stdin)
            except Exception:
                pass

    return await loop.run_in_executor(None, sys.stdin.readline)


async def _await_manual_input(
    on_manual_code_input: Callable[[str], None],
) -> str:
    await asyncio.sleep(MANUAL_PROMPT_DELAY_SEC)
    on_manual_code_input("Paste the authorization code (or full redirect URL), or wait for the browser callback:")
    return await _read_stdin_line()


def login_codex_oauth_interactive(
    on_auth: Callable[[str], None] | None = None,
    on_prompt: Callable[[str], str] | None = None,
    on_status: Callable[[str], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_manual_code_input: Callable[[str], None] = None,
    originator: str = DEFAULT_ORIGINATOR,
) -> CodexToken:
    """Interactive login flow."""

    async def _login_async() -> CodexToken:
        verifier, challenge = _generate_pkce()
        state = _create_state()

        params = {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": originator,
        }
        url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

        loop = asyncio.get_running_loop()
        code_future: asyncio.Future[str] = loop.create_future()

        def _notify(code_value: str) -> None:
            if code_future.done():
                return
            loop.call_soon_threadsafe(code_future.set_result, code_value)

        server, server_error = _start_local_server(state, on_code=_notify)
        if on_auth:
            on_auth(url)
        else:
            webbrowser.open(url)

        if not server and server_error and on_status:
            on_status(
                f"Local callback server could not start ({server_error}). "
                "You will need to paste the callback URL or authorization code."
            )

        code: str | None = None
        try:
            if server:
                if on_progress and not on_manual_code_input:
                    on_progress("Waiting for browser callback...")

                tasks: list[asyncio.Task[Any]] = []
                callback_task = asyncio.create_task(asyncio.wait_for(code_future, timeout=120))
                tasks.append(callback_task)
                manual_task = asyncio.create_task(_await_manual_input(on_manual_code_input))
                tasks.append(manual_task)

                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()

                for task in done:
                    try:
                        result = task.result()
                    except asyncio.TimeoutError:
                        result = None
                    if not result:
                        continue
                    if task is manual_task:
                        parsed_code, parsed_state = _parse_authorization_input(result)
                        if parsed_state and parsed_state != state:
                            raise RuntimeError("State validation failed.")
                        code = parsed_code
                    else:
                        code = result
                    if code:
                        break

            if not code:
                prompt = "Please paste the callback URL or authorization code:"
                if on_prompt:
                    raw = await loop.run_in_executor(None, on_prompt, prompt)
                else:
                    raw = await loop.run_in_executor(None, input, prompt)
                parsed_code, parsed_state = _parse_authorization_input(raw)
                if parsed_state and parsed_state != state:
                    raise RuntimeError("State validation failed.")
                code = parsed_code

            if not code:
                raise RuntimeError("Authorization code not found.")

            if on_progress:
                on_progress("Exchanging authorization code for tokens...")
            token = await _exchange_code_for_token_async(code, verifier)
            _save_token_file(token)
            return token
        finally:
            if server:
                server.shutdown()
                server.server_close()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_login_async())

    result: list[CodexToken] = []
    error: list[Exception] = []

    def _runner() -> None:
        try:
            result.append(asyncio.run(_login_async()))
        except Exception as exc:
            error.append(exc)

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]
