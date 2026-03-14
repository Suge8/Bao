from __future__ import annotations

import asyncio
import concurrent.futures
import re
import shutil
from collections.abc import Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from app.backend.asyncio_runner import AsyncioRunner
from bao.agent.skill_catalog import SkillCatalog
from bao.agent.skill_registry import build_skill_workspace_snapshot

_SKILL_REF_RE = re.compile(r"([A-Za-z0-9._-]+/[A-Za-z0-9._-]+@[A-Za-z0-9._-]+)")


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value
    return None


class SkillDiscoveryProvider:
    async def search(self, query: str) -> dict[str, object]:
        raise NotImplementedError

    async def install(self, *, reference: str, workspace_path: Path) -> dict[str, object]:
        raise NotImplementedError


class NpxSkillDiscoveryProvider(SkillDiscoveryProvider):
    async def search(self, query: str) -> dict[str, object]:
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
        items = SkillsService.parse_search_output(output)
        return {"items": items, "raw": output}

    async def install(self, *, reference: str, workspace_path: Path) -> dict[str, object]:
        workspace_root = workspace_path / "skills"
        workspace_root.mkdir(parents=True, exist_ok=True)
        source_root = workspace_path / ".agents" / "skills"
        before_names = SkillsService._snapshot_skill_names(source_root)
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
            cwd=str(workspace_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                (stderr or stdout).decode("utf-8", errors="replace").strip() or "skills add failed"
            )

        after_names = SkillsService._snapshot_skill_names(source_root)
        target_names = sorted(after_names - before_names)
        if not target_names:
            reference_name = SkillsService._extract_reference_name(reference)
            if reference_name and reference_name in after_names:
                target_names = [reference_name]
        imported_ids = SkillsService._copy_installed_skills(
            workspace_path=workspace_path,
            source_root=source_root,
            target_names=target_names or None,
        )
        if not imported_ids:
            raise RuntimeError("No installed skills were produced by skills add.")
        preferred_id = imported_ids[0]
        reference_name = SkillsService._extract_reference_name(reference)
        if reference_name:
            candidate_id = f"workspace:{reference_name}"
            if candidate_id in imported_ids:
                preferred_id = candidate_id
        return {"preferredId": preferred_id, "importedIds": imported_ids}


@dataclass(frozen=True)
class DiscoveryTaskState:
    state: str = "idle"
    kind: str = ""
    message: str = ""
    reference: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "state": self.state,
            "kind": self.kind,
            "message": self.message,
            "reference": self.reference,
        }


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
        discovery_provider: SkillDiscoveryProvider | None = None,
        eager_refresh: bool = True,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._runner: AsyncioRunner = runner
        self._workspace_path: Path = Path(workspace_path).expanduser()
        self._catalog: SkillCatalog = SkillCatalog(self._workspace_path)
        self._config_data: dict[str, object] = {}
        self._overview: dict[str, object] = {}
        self._discovery_provider = discovery_provider or NpxSkillDiscoveryProvider()
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
        self._discover_task: DiscoveryTaskState = DiscoveryTaskState()
        self._hydrated = False

        self._runnerResult.connect(self._handle_runner_result)
        if eager_refresh:
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

    @Property(dict, notify=changed)
    def overview(self) -> dict[str, object]:
        return dict(self._overview)

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
        return sum(1 for item in self._skills if bool(item.get("needsAttention")))

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

    @Property(dict, notify=changed)
    def discoverTask(self) -> dict[str, str]:
        return self._discover_task.to_dict()

    @Property(str, notify=changed)
    def discoverTaskState(self) -> str:
        return self._discover_task.state

    @Property(str, notify=changed)
    def discoverTaskMessage(self) -> str:
        return self._discover_task.message

    @Property(str, notify=changed)
    def discoverTaskKind(self) -> str:
        return self._discover_task.kind

    @Property(str, notify=changed)
    def discoverTaskReference(self) -> str:
        return self._discover_task.reference

    @Slot()
    def refresh(self) -> None:
        self._refresh()

    @Slot()
    def hydrateIfNeeded(self) -> None:
        self._refresh_if_hydrated(force=not self._hydrated)

    @Slot("QVariant")
    def setConfigData(self, data: object) -> None:
        next_data = _as_dict(data) or {}
        self._config_data = dict(next_data)
        self._refresh_if_hydrated()

    @Slot(str)
    def setQuery(self, value: str) -> None:
        next_value = value.strip()
        if next_value == self._query:
            return
        self._query = next_value
        self._refresh()

    @Slot(str)
    def setSourceFilter(self, value: str) -> None:
        next_value = (
            value
            if value in {"all", "workspace", "ready", "needs_setup", "instruction_only", "shadowed"}
            else "all"
        )
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
        self._set_discover_task(
            state="working",
            kind="search",
            message=f"Searching for '{query}'",
            reference=query,
        )
        self._submit_task("search_remote", self._search_remote(query))

    @Slot(result=bool)
    def installDiscoverReference(self) -> bool:
        reference = self._discover_reference.strip()
        if not reference:
            self._set_error("Skill reference is required.")
            self.operationFinished.emit("Skill reference is required.", False)
            return False
        self._set_discover_task(
            state="working",
            kind="install",
            message=f"Importing {reference}",
            reference=reference,
        )
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
        self._refresh_if_hydrated()

    def _refresh_if_hydrated(self, *, force: bool = False) -> None:
        if not force and not self._hydrated:
            return
        self._refresh()

    def _refresh(self, *, preferred_skill_id: str | None = None) -> None:
        snapshot = build_skill_workspace_snapshot(
            catalog=self._catalog,
            config_data=self._config_data,
            query=self._query.lower(),
            source_filter=self._source_filter,
            selected_id=preferred_skill_id or self._selected_skill_id,
        )
        self._hydrated = True
        self._skills = [dict(item) for item in snapshot.items]
        self._overview = dict(snapshot.overview)
        self._selected_skill_id = snapshot.selected_id
        self._selected_skill = dict(snapshot.selected_item)
        if self._selected_skill_id:
            source = str(self._selected_skill.get("source") or "")
            name = str(self._selected_skill.get("name") or "")
            self._selected_content = self._catalog.read_content(name, source)
        else:
            self._selected_content = ""
        self.changed.emit()

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
            task_kind = self._task_kind_for_operation(kind)
            self._set_discover_task(
                state="cancelled" if message == "cancelled" else "failed",
                kind=task_kind,
                message=message or self._cancel_message(task_kind),
                reference=self._discover_task.reference,
            )
            self.operationFinished.emit(message, False)
            return

        self._set_error("")

        if kind == "search_remote":
            result = payload if isinstance(payload, dict) else {}
            items = result.get("items", []) if isinstance(result, dict) else []
            self._set_discover_results(items)
            count = len(self._discover_results)
            self._set_discover_task(
                state="completed",
                kind="search",
                message=f"Found {count} candidate skills" if count else "No matching skills found",
                reference=self._discover_query.strip(),
            )
            self.changed.emit()
            self.operationFinished.emit("search_ok", True)
            return

        if kind == "install_reference":
            result = payload if isinstance(payload, dict) else {}
            preferred_id = str(result.get("preferredId") or "")
            self._refresh(preferred_skill_id=preferred_id)
            imported_ids = [str(item) for item in (result.get("importedIds", []) if isinstance(result, dict) else [])]
            self._mark_discover_installed(imported_ids)
            self._set_discover_task(
                state="completed",
                kind="install",
                message=f"Imported {len(imported_ids) or 1} skill into the workspace",
                reference=self._discover_reference.strip(),
            )
            self.operationFinished.emit("installed", True)

    async def _search_remote(self, query: str) -> dict[str, object]:
        return await self._discovery_provider.search(query)

    async def _install_reference(self, reference: str) -> dict[str, object]:
        return await self._discovery_provider.install(
            reference=reference,
            workspace_path=self._workspace_path,
        )

    def _import_installed_skills(
        self, source_root: Path, *, target_names: list[str] | None = None
    ) -> list[str]:
        return self._copy_installed_skills(
            workspace_path=self._workspace_path,
            source_root=source_root,
            target_names=target_names,
        )

    @staticmethod
    def _copy_installed_skills(
        *,
        workspace_path: Path,
        source_root: Path,
        target_names: list[str] | None = None,
    ) -> list[str]:
        if not source_root.exists():
            return []
        imported_ids: list[str] = []
        destination_root = workspace_path / "skills"
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

    def _mark_discover_installed(self, imported_ids: list[str]) -> None:
        if not imported_ids:
            return
        imported_names = {
            item.split(":", 1)[1]
            for item in imported_ids
            if ":" in item
        }
        next_results: list[dict[str, object]] = []
        next_selected = self._selected_discover_item
        for item in self._discover_results:
            next_item = dict(item)
            if str(next_item.get("name") or "") in imported_names:
                next_item["installState"] = "installed"
                next_item["installStateLabel"] = {"zh": "已导入", "en": "Installed"}
                next_item["installStateDetail"] = {
                    "zh": "该技能已经导入到当前工作区。",
                    "en": "This skill has been imported into the current workspace.",
                }
            next_results.append(next_item)
            if str(next_item.get("id") or "") == self._selected_discover_id:
                next_selected = next_item
        self._discover_results = next_results
        self._selected_discover_item = dict(next_selected)

    def _set_discover_task(
        self,
        *,
        state: str,
        kind: str,
        message: str,
        reference: str,
    ) -> None:
        next_task = DiscoveryTaskState(
            state=state,
            kind=kind,
            message=message,
            reference=reference,
        )
        if next_task != self._discover_task:
            self._discover_task = next_task
            self.changed.emit()

    @staticmethod
    def _task_kind_for_operation(kind: str) -> str:
        if kind == "search_remote":
            return "search"
        if kind == "install_reference":
            return "install"
        return ""

    @staticmethod
    def _cancel_message(kind: str) -> str:
        if kind == "search":
            return "Search cancelled"
        if kind == "install":
            return "Import cancelled"
        return ""

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
            owner, _slash, repo_name = repo.partition("/")
            title = skill_name.replace("-", " ").replace("_", " ").strip().title() or ref
            items.append(
                {
                    "id": ref,
                    "reference": ref,
                    "name": skill_name or ref,
                    "title": title,
                    "repo": repo,
                    "publisher": owner,
                    "repoName": repo_name,
                    "version": "latest",
                    "summary": f"Import {title} from {repo}",
                    "trustNote": {
                        "zh": "来自公开 skills registry；导入前请检查来源和说明。",
                        "en": "Listed in the public skills registry; review the source and instructions before importing.",
                    },
                    "requires": ["npx skills"],
                    "installState": "available",
                    "installStateLabel": {"zh": "可导入", "en": "Ready to import"},
                    "installStateDetail": {
                        "zh": "可直接导入到当前工作区。",
                        "en": "Ready to import into the current workspace.",
                    },
                    "searchText": f"{ref} {skill_name} {repo} {title} {owner} {repo_name}".lower(),
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
