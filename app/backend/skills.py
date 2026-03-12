from __future__ import annotations

import asyncio
import concurrent.futures
import re
import shutil
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from app.backend.asyncio_runner import AsyncioRunner
from bao.agent.skill_catalog import SkillCatalog

_SKILL_REF_RE = re.compile(r"([A-Za-z0-9._-]+/[A-Za-z0-9._-]+@[A-Za-z0-9._-]+)")


class SkillsService(QObject):
    changed: ClassVar[Signal] = Signal()
    busyChanged: ClassVar[Signal] = Signal()
    errorChanged: ClassVar[Signal] = Signal(str)
    operationFinished: ClassVar[Signal] = Signal(str, bool)

    _runnerResult: ClassVar[Signal] = Signal(str, bool, str, object)

    def __init__(
        self,
        runner: AsyncioRunner,
        workspace_path: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._runner: AsyncioRunner = runner
        self._workspace_path: Path = Path(workspace_path).expanduser()
        self._catalog: SkillCatalog = SkillCatalog(self._workspace_path)
        self._query: str = ""
        self._source_filter: str = "all"
        self._busy: bool = False
        self._busy_count: int = 0
        self._error: str = ""

        self._skills: list[dict[str, object]] = []
        self._selected_skill_id: str = ""
        self._selected_skill: dict[str, object] = {}
        self._selected_content: str = ""

        self._discover_query: str = ""
        self._discover_reference: str = ""
        self._discover_results: list[dict[str, object]] = []
        self._selected_discover_id: str = ""
        self._selected_discover_item: dict[str, object] = {}

        self._runnerResult.connect(self._handle_runner_result)
        self._refresh()

    @Property(str, notify=changed)
    def workspacePath(self) -> str:
        return str(self._workspace_path)

    @Property(str, notify=changed)
    def query(self) -> str:
        return self._query

    @Property(str, notify=changed)
    def sourceFilter(self) -> str:
        return self._source_filter

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=errorChanged)
    def lastError(self) -> str:
        return self._error

    @Property(list, notify=changed)
    def skills(self) -> list[dict[str, object]]:
        return list(self._skills)

    @Property(dict, notify=changed)
    def selectedSkill(self) -> dict[str, object]:
        return dict(self._selected_skill)

    @Property(str, notify=changed)
    def selectedSkillId(self) -> str:
        return self._selected_skill_id

    @Property(str, notify=changed)
    def selectedContent(self) -> str:
        return self._selected_content

    @Property(int, notify=changed)
    def totalCount(self) -> int:
        return len(self._skills)

    @Property(int, notify=changed)
    def workspaceCount(self) -> int:
        return sum(1 for item in self._skills if item.get("source") == "workspace")

    @Property(int, notify=changed)
    def builtinCount(self) -> int:
        return sum(1 for item in self._skills if item.get("source") == "builtin")

    @Property(int, notify=changed)
    def attentionCount(self) -> int:
        return sum(
            1
            for item in self._skills
            if not bool(item.get("available")) or bool(item.get("shadowed"))
        )

    @Property(str, notify=changed)
    def discoverQuery(self) -> str:
        return self._discover_query

    @Property(str, notify=changed)
    def discoverReference(self) -> str:
        return self._discover_reference

    @Property(list, notify=changed)
    def discoverResults(self) -> list[dict[str, object]]:
        return list(self._discover_results)

    @Property(dict, notify=changed)
    def selectedDiscoverItem(self) -> dict[str, object]:
        return dict(self._selected_discover_item)

    @Property(str, notify=changed)
    def selectedDiscoverId(self) -> str:
        return self._selected_discover_id

    @Slot()
    def refresh(self) -> None:
        self._refresh()

    @Slot(str)
    def setQuery(self, value: str) -> None:
        next_value = value.strip()
        if next_value == self._query:
            return
        self._query = next_value
        self._refresh()

    @Slot(str)
    def setSourceFilter(self, value: str) -> None:
        next_value = value if value in {"all", "workspace", "builtin", "attention"} else "all"
        if next_value == self._source_filter:
            return
        self._source_filter = next_value
        self._refresh()

    @Slot(str)
    def selectSkill(self, skill_id: str) -> None:
        self._set_selected(skill_id)

    @Slot(str)
    def setDiscoverQuery(self, value: str) -> None:
        next_value = value.strip()
        if next_value == self._discover_query:
            return
        self._discover_query = next_value
        self.changed.emit()

    @Slot(str)
    def setDiscoverReference(self, value: str) -> None:
        next_value = value.strip()
        if next_value == self._discover_reference:
            return
        self._discover_reference = next_value
        self.changed.emit()

    @Slot(str)
    def selectDiscoverItem(self, item_id: str) -> None:
        target = next((item for item in self._discover_results if item.get("id") == item_id), None)
        if target is None:
            return
        self._set_selected_discover_item(dict(target))
        self.changed.emit()

    @Slot()
    def searchRemote(self) -> None:
        query = self._discover_query.strip()
        if not query:
            self._set_error("Search query is required.")
            self.operationFinished.emit("Search query is required.", False)
            return
        self._submit_task("search_remote", self._search_remote(query))

    @Slot(result=bool)
    def installDiscoverReference(self) -> bool:
        reference = self._discover_reference.strip()
        if not reference:
            self._set_error("Skill reference is required.")
            self.operationFinished.emit("Skill reference is required.", False)
            return False
        self._submit_task("install_reference", self._install_reference(reference))
        return True

    @Slot(str, str, result=bool)
    def createSkill(self, name: str, description: str) -> bool:
        try:
            record = self._catalog.create_workspace_skill(name, description)
        except Exception as exc:
            self.operationFinished.emit(str(exc), False)
            return False
        self._refresh(preferred_skill_id=str(record.get("id") or ""))
        self.operationFinished.emit("created", True)
        return True

    @Slot(result=bool)
    def forkSelectedSkill(self) -> bool:
        skill = self._selected_skill
        if skill.get("source") != "builtin":
            self.operationFinished.emit("Only built-in skills can be forked.", False)
            return False
        try:
            record = self._catalog.fork_builtin_skill(str(skill.get("name") or ""))
        except Exception as exc:
            self.operationFinished.emit(str(exc), False)
            return False
        self._refresh(preferred_skill_id=str(record.get("id") or ""))
        self.operationFinished.emit("forked", True)
        return True

    @Slot(str, result=bool)
    def saveSelectedContent(self, content: str) -> bool:
        skill = self._selected_skill
        if skill.get("source") != "workspace":
            self.operationFinished.emit("Only workspace skills can be edited.", False)
            return False
        try:
            record = self._catalog.update_workspace_skill(str(skill.get("name") or ""), content)
        except Exception as exc:
            self.operationFinished.emit(str(exc), False)
            return False
        self._refresh(preferred_skill_id=str(record.get("id") or ""))
        self.operationFinished.emit("saved", True)
        return True

    @Slot(result=bool)
    def deleteSelectedSkill(self) -> bool:
        skill = self._selected_skill
        if skill.get("source") != "workspace":
            self.operationFinished.emit("Only workspace skills can be deleted.", False)
            return False
        deleted_name = str(skill.get("name") or "")
        try:
            self._catalog.delete_workspace_skill(deleted_name)
        except Exception as exc:
            self.operationFinished.emit(str(exc), False)
            return False
        self._refresh()
        self.operationFinished.emit("deleted", True)
        return True

    @Slot(result=bool)
    def openSelectedFolder(self) -> bool:
        target = self._selected_skill.get("path")
        if not isinstance(target, str) or not target:
            return False
        skill_file = Path(target)
        if not skill_file.exists():
            return False
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(skill_file.parent)))

    @Slot(result=bool)
    def openWorkspaceFolder(self) -> bool:
        target = self._workspace_path / "skills"
        target.mkdir(parents=True, exist_ok=True)
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    @Slot(result=bool)
    def openSkillsRegistry(self) -> bool:
        return QDesktopServices.openUrl(QUrl("https://skills.sh/"))

    @Slot(str)
    def setWorkspacePath(self, workspace_path: str) -> None:
        next_path = Path(workspace_path).expanduser()
        if next_path == self._workspace_path:
            return
        self._workspace_path = next_path
        self._catalog = SkillCatalog(self._workspace_path)
        self._refresh()

    def _refresh(self, *, preferred_skill_id: str | None = None) -> None:
        records = self._catalog.list_records()
        filtered = [item for item in records if self._matches_filters(item)]
        self._skills = filtered
        selected_id = preferred_skill_id or self._selected_skill_id
        if selected_id and any(item.get("id") == selected_id for item in filtered):
            self._set_selected(selected_id, emit=False)
        elif filtered:
            self._set_selected(str(filtered[0].get("id") or ""), emit=False)
        else:
            self._selected_skill_id = ""
            self._selected_skill = {}
            self._selected_content = ""
        self.changed.emit()

    def _matches_filters(self, item: dict[str, object]) -> bool:
        if self._source_filter == "workspace" and item.get("source") != "workspace":
            return False
        if self._source_filter == "builtin" and item.get("source") != "builtin":
            return False
        if self._source_filter == "attention":
            if bool(item.get("available")) and not bool(item.get("shadowed")):
                return False
        if not self._query:
            return True
        haystack = " ".join(
            str(item.get(field) or "")
            for field in ("name", "description", "source", "missingRequirements")
        ).lower()
        return self._query.lower() in haystack

    def _set_selected(self, skill_id: str, *, emit: bool = True) -> None:
        target = next((item for item in self._skills if item.get("id") == skill_id), None)
        if target is None:
            return
        self._selected_skill_id = skill_id
        self._selected_skill = dict(target)
        source = str(target.get("source") or "")
        name = str(target.get("name") or "")
        self._selected_content = self._catalog.read_content(name, source)
        if emit:
            self.changed.emit()

    def _submit_task(self, kind: str, coro: Coroutine[Any, Any, Any]) -> None:
        try:
            future = self._runner.submit(coro)
        except RuntimeError:
            coro.close()
            self._set_error("Asyncio runner is not available.")
            return
        self._set_busy(True)
        future.add_done_callback(lambda f, task_kind=kind: self._emit_runner_result(task_kind, f))

    def _emit_runner_result(self, kind: str, future: concurrent.futures.Future[Any]) -> None:
        try:
            payload = future.result()
            self._runnerResult.emit(kind, True, "", payload)
        except asyncio.CancelledError:
            self._runnerResult.emit(kind, False, "cancelled", None)
        except Exception as exc:
            self._runnerResult.emit(kind, False, str(exc), None)

    @Slot(str, bool, str, object)
    def _handle_runner_result(self, kind: str, ok: bool, message: str, payload: object) -> None:
        self._set_busy(False)
        if not ok:
            self._set_error(message)
            self.operationFinished.emit(message, False)
            return

        self._set_error("")

        if kind == "search_remote":
            result = payload if isinstance(payload, dict) else {}
            items = result.get("items", []) if isinstance(result, dict) else []
            self._set_discover_results(items)
            self.changed.emit()
            self.operationFinished.emit("search_ok", True)
            return

        if kind == "install_reference":
            result = payload if isinstance(payload, dict) else {}
            preferred_id = str(result.get("preferredId") or "")
            self._refresh(preferred_skill_id=preferred_id)
            self.operationFinished.emit("installed", True)

    async def _search_remote(self, query: str) -> dict[str, object]:
        process = await asyncio.create_subprocess_exec(
            "npx",
            "--yes",
            "skills",
            "find",
            query,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                (stderr or stdout).decode("utf-8", errors="replace").strip() or "skills find failed"
            )
        output = stdout.decode("utf-8", errors="replace")
        items = self.parse_search_output(output)
        return {"items": items, "raw": output}

    async def _install_reference(self, reference: str) -> dict[str, object]:
        workspace_root = self._workspace_path / "skills"
        workspace_root.mkdir(parents=True, exist_ok=True)
        source_root = self._workspace_path / ".agents" / "skills"
        before_names = self._snapshot_skill_names(source_root)
        process = await asyncio.create_subprocess_exec(
            "npx",
            "--yes",
            "skills",
            "add",
            reference,
            "--agent",
            "codex",
            "--copy",
            "-y",
            cwd=str(self._workspace_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                (stderr or stdout).decode("utf-8", errors="replace").strip() or "skills add failed"
            )

        after_names = self._snapshot_skill_names(source_root)
        target_names = sorted(after_names - before_names)
        if not target_names:
            reference_name = self._extract_reference_name(reference)
            if reference_name and reference_name in after_names:
                target_names = [reference_name]
        imported_ids = self._import_installed_skills(source_root, target_names=target_names or None)
        if not imported_ids:
            raise RuntimeError("No installed skills were produced by skills add.")
        preferred_id = imported_ids[0]
        reference_name = self._extract_reference_name(reference)
        if reference_name:
            candidate_id = f"workspace:{reference_name}"
            if candidate_id in imported_ids:
                preferred_id = candidate_id
        return {"preferredId": preferred_id, "importedIds": imported_ids}

    def _import_installed_skills(
        self, source_root: Path, *, target_names: list[str] | None = None
    ) -> list[str]:
        if not source_root.exists():
            return []
        imported_ids: list[str] = []
        destination_root = self._workspace_path / "skills"
        destination_root.mkdir(parents=True, exist_ok=True)
        allowed_names = set(target_names or [])
        for skill_dir in sorted(source_root.iterdir(), key=lambda item: item.name.lower()):
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
                continue
            if allowed_names and skill_dir.name not in allowed_names:
                continue
            destination = destination_root / skill_dir.name
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(skill_dir, destination)
            imported_ids.append(f"workspace:{skill_dir.name}")
        return imported_ids

    def _set_discover_results(self, items: object) -> None:
        raw_items = items if isinstance(items, list) else []
        self._discover_results = [dict(item) for item in raw_items if isinstance(item, dict)]
        if not self._discover_results:
            self._selected_discover_id = ""
            self._selected_discover_item = {}
            return
        self._set_selected_discover_item(dict(self._discover_results[0]))

    def _set_selected_discover_item(self, item: dict[str, object]) -> None:
        self._selected_discover_item = dict(item)
        self._selected_discover_id = str(item.get("id") or "")
        reference = str(item.get("reference") or "")
        if reference:
            self._discover_reference = reference

    @staticmethod
    def _snapshot_skill_names(source_root: Path) -> set[str]:
        if not source_root.exists():
            return set()
        return {
            skill_dir.name
            for skill_dir in source_root.iterdir()
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists()
        }

    @staticmethod
    def _extract_reference_name(reference: str) -> str:
        _repo, _sep, skill_name = reference.partition("@")
        return skill_name.strip()

    @staticmethod
    def parse_search_output(output: str) -> list[dict[str, object]]:
        refs = list(dict.fromkeys(_SKILL_REF_RE.findall(output)))
        items: list[dict[str, object]] = []
        for ref in refs:
            repo, _sep, skill_name = ref.partition("@")
            items.append(
                {
                    "id": ref,
                    "reference": ref,
                    "name": skill_name or ref,
                    "repo": repo,
                    "summary": f"Install with npx skills add {ref}",
                    "searchText": f"{ref} {skill_name} {repo}".lower(),
                }
            )
        return items

    def _set_busy(self, active: bool) -> None:
        self._busy_count = max(0, self._busy_count + (1 if active else -1))
        next_busy = self._busy_count > 0
        if next_busy == self._busy:
            return
        self._busy = next_busy
        self.busyChanged.emit()

    def _set_error(self, message: str) -> None:
        if message == self._error:
            return
        self._error = message
        self.errorChanged.emit(message)
