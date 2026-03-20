"""Email fetch helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from typing import Any


@dataclass(frozen=True)
class _EmailFetchRequest:
    search_criteria: tuple[str, ...]
    mark_seen: bool
    dedupe: bool
    limit: int


@dataclass(frozen=True)
class _EmailFetchItemRequest:
    client: Any
    imap_id: bytes
    mark_seen: bool
    dedupe: bool


class _EmailFetchMixin:
    def _fetch_new_messages(self) -> list[dict[str, Any]]:
        return self._fetch_messages(
            _EmailFetchRequest(
                search_criteria=("UNSEEN",),
                mark_seen=self.config.mark_seen,
                dedupe=True,
                limit=0,
            )
        )

    def fetch_messages_between_dates(
        self,
        start_date: date,
        end_date: date,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if end_date <= start_date:
            return []
        return self._fetch_messages(
            _EmailFetchRequest(
                search_criteria=(
                    "SINCE",
                    self._format_imap_date(start_date),
                    "BEFORE",
                    self._format_imap_date(end_date),
                ),
                mark_seen=False,
                dedupe=False,
                limit=max(1, int(limit)),
            )
        )

    def _fetch_messages(self, request: _EmailFetchRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        mailbox = self.config.imap_mailbox or "INBOX"
        imap_password = self.config.imap_password.get_secret_value()

        client = self._connect_imap()
        try:
            client.login(self.config.imap_username, imap_password)
            status, _ = client.select(mailbox)
            if status != "OK":
                return messages

            status, data = client.search(None, *request.search_criteria)
            if status != "OK" or not data:
                return messages

            ids = data[0].split()
            if request.limit > 0 and len(ids) > request.limit:
                ids = ids[-request.limit :]
            for imap_id in ids:
                item = self._fetch_single_message(
                    _EmailFetchItemRequest(
                        client=client,
                        imap_id=imap_id,
                        mark_seen=request.mark_seen,
                        dedupe=request.dedupe,
                    )
                )
                if item is not None:
                    messages.append(item)
        finally:
            try:
                client.logout()
            except Exception:
                pass
        return messages

    def _connect_imap(self):
        from . import email as email_module

        if self.config.imap_use_ssl:
            return email_module.imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port)
        return email_module.imaplib.IMAP4(self.config.imap_host, self.config.imap_port)

    def _fetch_single_message(self, request: _EmailFetchItemRequest) -> dict[str, Any] | None:
        status, fetched = request.client.fetch(request.imap_id, "(BODY.PEEK[] UID)")
        if status != "OK" or not fetched:
            return None

        raw_bytes = self._extract_message_bytes(fetched)
        if raw_bytes is None:
            return None

        uid = self._extract_uid(fetched)
        if request.dedupe and uid and uid in self._processed_uids:
            return None

        parsed = BytesParser(policy=policy.default).parsebytes(raw_bytes)
        sender = parseaddr(parsed.get("From", ""))[1].strip().lower()
        if not sender:
            return None

        item = self._build_inbound_item(parsed, sender, uid)
        if request.dedupe and uid:
            self._remember_uid(uid)
        if request.mark_seen:
            request.client.store(request.imap_id, "+FLAGS", "\\Seen")
        return item

    def _build_inbound_item(self, parsed, sender: str, uid: str) -> dict[str, Any]:
        subject = self._decode_header_value(parsed.get("Subject", ""))
        date_value = parsed.get("Date", "")
        message_id = parsed.get("Message-ID", "").strip()
        body = self._extract_text_body(parsed) or "(empty email body)"
        body = body[: self.config.max_body_chars]
        content = (
            f"Email received.\n"
            f"From: {sender}\n"
            f"Subject: {subject}\n"
            f"Date: {date_value}\n\n"
            f"{body}"
        )
        metadata = {
            "message_id": message_id,
            "subject": subject,
            "date": date_value,
            "sender_email": sender,
            "uid": uid,
        }
        return {
            "sender": sender,
            "subject": subject,
            "message_id": message_id,
            "content": content,
            "metadata": metadata,
        }

    def _remember_uid(self, uid: str) -> None:
        self._processed_uids.add(uid)
        if len(self._processed_uids) > self._MAX_PROCESSED_UIDS:
            self._processed_uids = set(list(self._processed_uids)[len(self._processed_uids) // 2 :])
