from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from bao.agent.skills import BUILTIN_SKILLS_DIR

_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$|^[a-z0-9]$")


@dataclass(frozen=True)
class SkillRecord:
    id: str
    name: str
    source: str
    path: str
    description: str
    available: bool
    missing_requirements: str
    always: bool
    shadowed: bool
    emoji: str
    can_edit: bool
    can_delete: bool
    can_fork: bool
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "path": self.path,
            "description": self.description,
            "available": self.available,
            "missingRequirements": self.missing_requirements,
            "always": self.always,
            "shadowed": self.shadowed,
            "emoji": self.emoji,
            "canEdit": self.can_edit,
            "canDelete": self.can_delete,
            "canFork": self.can_fork,
            "metadata": dict(self.metadata),
        }


def normalize_skill_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized or not _SKILL_NAME_RE.fullmatch(normalized):
        raise ValueError("Skill name must use lowercase letters, digits, or hyphens.")
    return normalized


class SkillCatalog:
    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None) -> None:
        self.workspace: Path = workspace
        self.workspace_skills: Path = workspace / "skills"
        self.builtin_skills: Path = builtin_skills_dir or BUILTIN_SKILLS_DIR

    def list_records(self) -> list[dict[str, object]]:
        workspace_records = self._scan_source("workspace")
        workspace_names = {record.name for record in workspace_records}
        builtin_records = self._scan_source("builtin", shadowed_names=workspace_names)
        records = workspace_records + builtin_records
        records.sort(key=self._sort_key)
        return [record.to_dict() for record in records]

    def read_content(self, name: str, source: str) -> str:
        skill_file = self._skill_file(name, source)
        if not skill_file.exists():
            raise FileNotFoundError(f"Skill not found: {source}:{name}")
        return skill_file.read_text(encoding="utf-8")

    def create_workspace_skill(self, raw_name: str, description: str) -> dict[str, object]:
        name = normalize_skill_name(raw_name)
        skill_dir = self.workspace_skills / name
        skill_file = skill_dir / "SKILL.md"
        if skill_dir.exists() or skill_file.exists():
            raise ValueError(f"Skill already exists: {name}")

        _ = skill_dir.mkdir(parents=True, exist_ok=False)
        body = (
            f"---\n"
            f"name: {name}\n"
            f"description: {description.strip() or f'Use for {name} tasks.'}\n"
            f"---\n\n"
            f"# {name}\n\n"
            "Add the workflow, references, and usage guidance for this skill here.\n"
        )
        _ = skill_file.write_text(body, encoding="utf-8")
        return self._record_for(name, "workspace").to_dict()

    def fork_builtin_skill(
        self, name: str, destination_name: str | None = None
    ) -> dict[str, object]:
        builtin_dir = self.builtin_skills / name
        if not builtin_dir.exists():
            raise FileNotFoundError(f"Built-in skill not found: {name}")

        target_name = normalize_skill_name(destination_name or name)
        target_dir = self.workspace_skills / target_name
        if target_dir.exists():
            raise ValueError(f"Workspace skill already exists: {target_name}")

        _ = self.workspace_skills.mkdir(parents=True, exist_ok=True)
        _ = shutil.copytree(builtin_dir, target_dir)
        if target_name != name:
            skill_file = target_dir / "SKILL.md"
            content = skill_file.read_text(encoding="utf-8")
            content = re.sub(
                r"^name:\s*.*$", f"name: {target_name}", content, count=1, flags=re.MULTILINE
            )
            _ = skill_file.write_text(content, encoding="utf-8")
        return self._record_for(target_name, "workspace").to_dict()

    def update_workspace_skill(self, name: str, content: str) -> dict[str, object]:
        skill_file = self._skill_file(name, "workspace")
        if not skill_file.exists():
            raise FileNotFoundError(f"Workspace skill not found: {name}")
        _ = skill_file.write_text(content, encoding="utf-8")
        return self._record_for(name, "workspace").to_dict()

    def delete_workspace_skill(self, name: str) -> None:
        skill_dir = self.workspace_skills / name
        if not skill_dir.exists():
            raise FileNotFoundError(f"Workspace skill not found: {name}")
        shutil.rmtree(skill_dir)

    def _scan_source(
        self, source: str, *, shadowed_names: set[str] | None = None
    ) -> list[SkillRecord]:
        base_dir = self._source_dir(source)
        if not base_dir.exists():
            return []

        shadowed_names = shadowed_names or set()
        records: list[SkillRecord] = []
        for skill_dir in sorted(base_dir.iterdir(), key=lambda item: item.name.lower()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            records.append(
                self._record_for(skill_dir.name, source, shadowed=skill_dir.name in shadowed_names)
            )
        return records

    def _record_for(self, name: str, source: str, *, shadowed: bool = False) -> SkillRecord:
        skill_file = self._skill_file(name, source)
        content = skill_file.read_text(encoding="utf-8")
        metadata = self._get_file_metadata(content)
        description = metadata.get("description") or name
        skill_meta = self._parse_bao_metadata(metadata.get("metadata", ""))
        available = self._check_requirements(skill_meta)
        missing_requirements = self._get_missing_requirements(skill_meta)
        always = bool(skill_meta.get("always") or metadata.get("always") == "true")
        emoji = str(skill_meta.get("emoji") or "")
        return SkillRecord(
            id=f"{source}:{name}",
            name=name,
            source=source,
            path=str(skill_file),
            description=description,
            available=available,
            missing_requirements=missing_requirements,
            always=always,
            shadowed=shadowed,
            emoji=emoji,
            can_edit=source == "workspace",
            can_delete=source == "workspace",
            can_fork=source == "builtin",
            metadata=metadata,
        )

    @staticmethod
    def _get_file_metadata(content: str) -> dict[str, str]:
        if not content.startswith("---"):
            return {}
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return {}
        metadata: dict[str, str] = {}
        for line in match.group(1).split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip("\"'")
        return metadata

    def _source_dir(self, source: str) -> Path:
        if source == "workspace":
            return self.workspace_skills
        if source == "builtin":
            return self.builtin_skills
        raise ValueError(f"Unsupported skill source: {source}")

    def _skill_file(self, name: str, source: str) -> Path:
        return self._source_dir(source) / name / "SKILL.md"

    @staticmethod
    def _parse_bao_metadata(raw: str) -> dict[str, object]:
        try:
            import json

            data = json.loads(raw)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        payload = data.get("bao", data.get("openclaw", {}))
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _check_requirements(skill_meta: dict[str, object]) -> bool:
        requires = skill_meta.get("requires", {})
        if not isinstance(requires, dict):
            return True

        bins = requires.get("bins", [])
        if not isinstance(bins, list):
            bins = []
        for binary in bins:
            if isinstance(binary, str) and not shutil.which(binary):
                return False

        bins_any = requires.get("bins_any", [])
        if isinstance(bins_any, list) and bins_any:
            if not any(isinstance(binary, str) and shutil.which(binary) for binary in bins_any):
                return False

        envs = requires.get("env", [])
        if not isinstance(envs, list):
            envs = []
        for env_name in envs:
            if isinstance(env_name, str) and not os.environ.get(env_name):
                return False
        return True

    @staticmethod
    def _get_missing_requirements(skill_meta: dict[str, object]) -> str:
        missing: list[str] = []
        requires = skill_meta.get("requires", {})
        if not isinstance(requires, dict):
            return ""

        bins = requires.get("bins", [])
        if isinstance(bins, list):
            for binary in bins:
                if isinstance(binary, str) and not shutil.which(binary):
                    missing.append(f"CLI: {binary}")

        bins_any = requires.get("bins_any", [])
        if isinstance(bins_any, list) and bins_any:
            candidates = [binary for binary in bins_any if isinstance(binary, str)]
            if candidates and not any(shutil.which(binary) for binary in candidates):
                missing.append(f"CLI(any): {' | '.join(candidates)}")

        envs = requires.get("env", [])
        if isinstance(envs, list):
            for env_name in envs:
                if isinstance(env_name, str) and not os.environ.get(env_name):
                    missing.append(f"ENV: {env_name}")
        return ", ".join(missing)

    @staticmethod
    def _sort_key(record: SkillRecord) -> tuple[int, int, str]:
        source_rank = 0 if record.source == "workspace" else 1
        availability_rank = 0 if record.available else 1
        return (source_rank, availability_rank, record.name.lower())
