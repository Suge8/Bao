from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bao.agent._loop_tool_registry_sessions import register_session_handoff_tools
from bao.agent.tools.base import Tool
from bao.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from bao.agent.tools.plan import ClearPlanTool, CreatePlanTool, UpdatePlanStepTool
from bao.agent.tools.registry import ToolMetadata
from bao.agent.tools.shell import ExecTool, ExecToolOptions
from bao.agent.tools.spawn import SpawnTool
from bao.agent.tools.task_status import CancelTaskTool, CheckTasksJsonTool, CheckTasksTool


@dataclass(frozen=True, slots=True)
class ToolRegistrationOptions:
    bundle: str
    short_hint: str
    aliases: tuple[str, ...] = ()
    keyword_aliases: tuple[str, ...] = ()
    auto_callable: bool = True
    summary: str | None = None


def register_tool(
    loop: Any,
    tool: Tool,
    options: ToolRegistrationOptions,
) -> None:
    loop.tools.register(
        tool,
        metadata=ToolMetadata(
            bundle=options.bundle,
            short_hint=options.short_hint,
            aliases=options.aliases,
            keyword_aliases=options.keyword_aliases,
            auto_callable=options.auto_callable,
            summary=(options.summary or tool.description).strip(),
        ),
    )


def update_tool_metadata(loop: Any, name: str, *, short_hint: str | None = None) -> None:
    metadata = loop.tools.get_metadata(name)
    if metadata is None:
        return
    loop.tools.update_metadata(
        name,
        ToolMetadata(
            bundle=metadata.bundle,
            short_hint=short_hint or metadata.short_hint,
            aliases=metadata.aliases,
            keyword_aliases=metadata.keyword_aliases,
            auto_callable=metadata.auto_callable,
            summary=metadata.summary,
        ),
    )


def register_default_tools(loop: Any) -> None:
    from ._loop_tool_registry_memory import register_memory_and_cron_tools

    allowed_dir = loop.workspace if loop.restrict_to_workspace else None
    _register_core_tools(loop, allowed_dir)
    _register_image_tool(loop)
    _register_runtime_and_plan_tools(loop)
    register_memory_and_cron_tools(loop)


def _register_core_tools(loop: Any, allowed_dir: Path | None) -> None:
    register_tool(
        loop,
        ReadFileTool(workspace=loop.workspace, allowed_dir=allowed_dir),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Read a file from the workspace or allowed path.",
            aliases=("read file", "读取文件", "看文件"),
            keyword_aliases=("file", "path", "read", "读取"),
        ),
    )
    register_tool(
        loop,
        WriteFileTool(workspace=loop.workspace, allowed_dir=allowed_dir),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Write or create a file, including missing parent directories.",
            aliases=("write file", "创建文件", "写文件"),
            keyword_aliases=("write", "create", "保存", "写入"),
        ),
    )
    register_tool(
        loop,
        EditFileTool(workspace=loop.workspace, allowed_dir=allowed_dir),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Edit an existing file by exact text replacement.",
            aliases=("edit file", "修改文件", "替换文本"),
            keyword_aliases=("edit", "replace", "修改", "替换"),
        ),
    )
    register_tool(
        loop,
        ListDirTool(workspace=loop.workspace, allowed_dir=allowed_dir),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="List directory contents.",
            aliases=("list dir", "列目录", "查看目录"),
            keyword_aliases=("directory", "folder", "目录", "文件夹"),
        ),
    )
    register_tool(
        loop,
        ExecTool(
            ExecToolOptions(
                working_dir=str(loop.workspace),
                timeout=loop.exec_config.timeout,
                restrict_to_workspace=loop.restrict_to_workspace,
                path_append=loop.exec_config.path_append,
                sandbox_mode=loop.exec_config.sandbox_mode,
            )
        ),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Run shell commands on the Runtime host for local operations.",
            aliases=("run command", "shell", "命令行", "执行命令"),
            keyword_aliases=("command", "terminal", "bash", "run", "执行", "命令"),
        ),
    )


def _register_image_tool(loop: Any) -> None:
    image_api_key = (
        loop._image_generation_config.api_key.get_secret_value()
        if loop._image_generation_config
        else ""
    )
    if not loop._image_generation_config or not image_api_key:
        return
    from bao.agent.tools.image_gen import ImageGenTool

    register_tool(
        loop,
        ImageGenTool(
            api_key=image_api_key,
            model=loop._image_generation_config.model,
            base_url=loop._image_generation_config.base_url,
        ),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Create images from text prompts.",
            aliases=("generate image", "画图", "生成图片"),
            keyword_aliases=("image", "draw", "画", "图片"),
        ),
    )


def _register_runtime_and_plan_tools(loop: Any) -> None:
    register_session_handoff_tools(
        loop,
        register_tool_fn=register_tool,
        options_cls=ToolRegistrationOptions,
    )
    _register_plan_tools(loop)
    _register_subagent_tools(loop)


def _register_plan_tools(loop: Any) -> None:
    register_tool(
        loop,
        CreatePlanTool(sessions=loop.sessions, publish_outbound=loop.bus.publish_outbound),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Create a plan when work has 2+ meaningful steps or the user explicitly asks for one.",
            aliases=("create plan", "制定计划", "拆步骤"),
            keyword_aliases=("plan", "steps", "计划", "步骤"),
        ),
    )
    register_tool(
        loop,
        UpdatePlanStepTool(sessions=loop.sessions, publish_outbound=loop.bus.publish_outbound),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Update plan progress after each completed step.",
            aliases=("update plan", "更新计划", "推进步骤"),
            keyword_aliases=("plan", "progress", "更新", "进度"),
        ),
    )
    register_tool(
        loop,
        ClearPlanTool(sessions=loop.sessions, publish_outbound=loop.bus.publish_outbound),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Clear the active plan when the work is done or abandoned.",
            aliases=("clear plan", "清空计划"),
            keyword_aliases=("plan", "clear", "结束计划", "清空"),
        ),
    )


def _register_subagent_tools(loop: Any) -> None:
    spawn_tool = SpawnTool(manager=loop.subagents)
    spawn_tool.set_publish_outbound(loop.bus.publish_outbound)
    register_tool(
        loop,
        spawn_tool,
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Delegate multi-step or time-consuming work to a subagent.",
            aliases=("spawn task", "委派任务", "子代理"),
            keyword_aliases=("delegate", "subagent", "spawn", "委派"),
        ),
    )
    register_tool(
        loop,
        CheckTasksTool(manager=loop.subagents),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Check subagent progress only when the user explicitly asks.",
            aliases=("check tasks", "查看进度"),
            keyword_aliases=("progress", "status", "进度", "状态"),
            auto_callable=False,
        ),
    )
    register_tool(
        loop,
        CancelTaskTool(manager=loop.subagents),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Cancel a running subagent task when needed.",
            aliases=("cancel task", "取消任务"),
            keyword_aliases=("cancel", "stop", "取消"),
            auto_callable=False,
        ),
    )
    register_tool(
        loop,
        CheckTasksJsonTool(manager=loop.subagents),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Fetch structured subagent status when machine-readable progress is needed.",
            aliases=("check tasks json", "结构化任务状态"),
            keyword_aliases=("json", "structured", "结构化"),
            auto_callable=False,
        ),
    )
