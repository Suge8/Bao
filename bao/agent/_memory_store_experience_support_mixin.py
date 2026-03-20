from __future__ import annotations

from datetime import datetime


class _MemoryStoreExperienceSupportMixin:
    def _confidence(self, row: dict[str, object]) -> float:
        uses = row.get("uses", 0)
        successes = row.get("successes", 0)
        return (successes + 1) / (uses + 2)

    @staticmethod
    def _experience_preview(task: str, lessons: str) -> str:
        base = f"{task} — {lessons}" if task and lessons else (task or lessons)
        cleaned = base.replace("\n", " ").strip()
        if len(cleaned) <= 180:
            return cleaned
        return cleaned[:179].rstrip() + "…"

    def _experience_row_to_item(self, row: dict[str, object]) -> dict[str, object]:
        content = str(row.get("content") or "")
        task = self._extract_field(content, "Task")
        lessons = self._extract_field(content, "Lessons")
        keywords = self._extract_field(content, "Keywords")
        trace = self._extract_field(content, "Trace")
        return {
            "key": str(row.get("key") or ""),
            "task": task,
            "lessons": lessons,
            "keywords": keywords,
            "trace": trace,
            "content": content,
            "preview": self._experience_preview(task, lessons),
            "category": str(row.get("category") or "general"),
            "outcome": str(row.get("outcome") or ""),
            "quality": int(row.get("quality", 0) or 0),
            "uses": int(row.get("uses", 0) or 0),
            "successes": int(row.get("successes", 0) or 0),
            "deprecated": bool(row.get("deprecated", False)),
            "updated_at": str(row.get("updated_at", "")),
            "hit_count": int(row.get("hit_count", 0) or 0),
            "last_hit_at": str(row.get("last_hit_at", "")),
        }

    @staticmethod
    def _extract_field(content: str, prefix: str) -> str:
        for line in content.split("\n"):
            if line.startswith(f"{prefix}:"):
                return line.split(":", 1)[1].strip()
        return ""

    @staticmethod
    def _days_since(ts: str, now: datetime) -> float:
        if not ts:
            return 30.0
        try:
            return max(0.0, (now - datetime.fromisoformat(ts)).total_seconds() / 86400)
        except (ValueError, TypeError):
            return 30.0

    def _update_experience(self, row: dict[str, object], **updates) -> None:
        key = row.get("key")
        if not key:
            return
        self._tbl.delete(f"key = '{key}'")
        next_row = self._make_row(
            key=key,
            content=row.get("content", ""),
            type_="experience",
            category=row.get("category", ""),
            quality=row.get("quality", 3),
            uses=row.get("uses", 0),
            successes=row.get("successes", 0),
            outcome=row.get("outcome", ""),
            deprecated=row.get("deprecated", False),
            updated_at=datetime.now().isoformat(),
        )
        next_row.update(updates)
        self._tbl.add([next_row])
        self._invalidate_retrieval_index()

    def _match_experience_rows(self, task_desc: str, threshold: float) -> list[dict[str, object]]:
        rows = self._tbl.search().where("type = 'experience'").limit(100).to_list()
        keywords = {word.lower() for word in task_desc.split() if len(word) >= 2}
        if not keywords:
            return []
        results = []
        for row in rows:
            if row.get("deprecated"):
                continue
            content = str(row.get("content") or "").lower()
            hits = sum(1 for keyword in keywords if keyword in content)
            if hits >= len(keywords) * threshold:
                results.append(row)
        return results

    def _mutate_experiences(
        self,
        task_desc: str,
        threshold: float,
        mutator,
        action: str,
    ) -> int:
        from loguru import logger

        with self._store_lock:
            try:
                count = 0
                for row in self._match_experience_rows(task_desc, threshold=threshold):
                    updates = mutator(row)
                    if not updates:
                        continue
                    self._update_experience(row, **updates)
                    count += 1
                if count:
                    logger.info("📝 经验变更 / {}: {} for {}", action, count, task_desc[:60])
                return count
            except Exception as exc:
                logger.warning("⚠️ 经验变更失败 / {} failed: {}", action, exc)
                return 0
