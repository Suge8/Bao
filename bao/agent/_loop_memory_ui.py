from __future__ import annotations

import asyncio
from typing import Any


async def handle_memory_command(loop: Any, msg: Any, session: Any) -> Any:
    entries = await asyncio.to_thread(loop.context.memory.list_long_term_entries)
    if not entries:
        loop._clear_memory_state(session)
        await asyncio.to_thread(loop.sessions.save, session)
        return loop._reply(msg, "暂无记忆 📭")
    loop._clear_memory_state(session)
    session.metadata["_pending_memory_list"] = True
    session.metadata["_memory_entries"] = entries
    await asyncio.to_thread(loop.sessions.save, session)
    return loop._reply(msg, _memory_list_text(entries))


async def handle_memory_input(loop: Any, msg: Any, session: Any) -> Any:
    text = msg.content.strip()
    entries: list[dict[str, str]] = session.metadata.get("_memory_entries", [])
    if session.metadata.get("_pending_memory_edit"):
        return await _handle_memory_edit(loop, msg, session, text, entries)
    if session.metadata.get("_pending_memory_delete"):
        return await _handle_memory_delete(loop, msg, session, text, entries)
    if session.metadata.get("_pending_memory_detail"):
        return await _handle_memory_detail(loop, msg, session, text, entries)
    if session.metadata.get("_pending_memory_list"):
        return await _handle_memory_list_selection(loop, msg, session, text, entries)
    loop._clear_memory_state(session)
    loop.sessions.save(session)
    return loop._reply(msg, "已退出记忆管理 👌")


def _memory_list_text(entries: list[dict[str, str]]) -> str:
    by_category: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for index, entry in enumerate(entries, 1):
        category = entry.get("category", "general")
        by_category.setdefault(category, []).append((index, entry))
    lines = ["🧠 记忆列表:\n"]
    for category, items in by_category.items():
        lines.append(f"[{category}]")
        for index, entry in items:
            content = entry.get("content", "")
            preview = content[:60].replace("\n", " ")
            if len(content) > 60:
                preview += "..."
            lines.append(f"  {index}. {preview}")
        lines.append("")
    lines.append("输入编号查看详情，输入 0 进入删除模式，其他输入退出")
    return "\n".join(lines)


async def _handle_memory_edit(
    loop: Any,
    msg: Any,
    session: Any,
    text: str,
    entries: list[dict[str, str]],
) -> Any:
    index = session.metadata.get("_memory_selected_index", 0)
    if not (0 < index <= len(entries)):
        return _exit_memory(loop, msg, session, "无效操作，已退出记忆管理")
    entry = entries[index - 1]
    category = entry.get("category", "general")
    key = entry.get("key", "")
    key_exists = await asyncio.to_thread(loop.context.memory.exists_long_term_key, key)
    if not key or not key_exists:
        return _exit_memory(loop, msg, session, "该记忆已失效，请重新 /memory")
    if not text:
        return _exit_memory(loop, msg, session, "内容为空，已取消编辑")
    deleted_by_key = await asyncio.to_thread(loop.context.memory.delete_long_term_by_key, key)
    if not deleted_by_key:
        return _exit_memory(loop, msg, session, "该记忆已失效，请重新 /memory")
    await asyncio.to_thread(loop.context.memory.write_long_term, text, category)
    return _exit_memory(loop, msg, session, f"已更新 [{category}] 记忆 ✅")


async def _handle_memory_delete(
    loop: Any,
    msg: Any,
    session: Any,
    text: str,
    entries: list[dict[str, str]],
) -> Any:
    fresh = await asyncio.to_thread(loop.context.memory.list_long_term_entries)
    fresh_keys = {entry.get("key", "") for entry in fresh}
    deleted = 0
    skipped = 0
    for part in set(text.split()):
        if not part.isdigit():
            continue
        index = int(part)
        if not (0 < index <= len(entries)):
            continue
        key = entries[index - 1].get("key", "")
        if key and key not in fresh_keys:
            skipped += 1
            continue
        if not key:
            continue
        deleted_by_key = await asyncio.to_thread(loop.context.memory.delete_long_term_by_key, key)
        if deleted_by_key:
            deleted += 1
            fresh_keys.discard(key)
    if deleted:
        suffix = f"（{skipped} 条已失效跳过）" if skipped else ""
        return _exit_memory(loop, msg, session, f"已删除 {deleted} 条记忆 🗑️{suffix}")
    if skipped:
        return _exit_memory(loop, msg, session, f"{skipped} 条记忆已失效，未执行删除")
    return _exit_memory(loop, msg, session, "未删除任何记忆，已退出")


async def _handle_memory_detail(
    loop: Any,
    msg: Any,
    session: Any,
    text: str,
    entries: list[dict[str, str]],
) -> Any:
    if text == "9":
        session.metadata["_pending_memory_edit"] = True
        session.metadata.pop("_pending_memory_detail", None)
        loop.sessions.save(session)
        return loop._reply(msg, "请输入新内容替换该条记忆：")
    if text == "0":
        return await _delete_selected_memory(loop, msg, session, entries)
    return await handle_memory_command(loop, msg, session)


async def _delete_selected_memory(loop: Any, msg: Any, session: Any, entries: list[dict[str, str]]) -> Any:
    index = session.metadata.get("_memory_selected_index", 0)
    deleted = False
    if 0 < index <= len(entries):
        key = entries[index - 1].get("key", "")
        if key:
            fresh = await asyncio.to_thread(loop.context.memory.list_long_term_entries)
            fresh_keys = {entry.get("key", "") for entry in fresh}
            if key not in fresh_keys:
                return _exit_memory(loop, msg, session, "该记忆已失效，无需删除")
            deleted = await asyncio.to_thread(loop.context.memory.delete_long_term_by_key, key)
    if deleted:
        return _exit_memory(loop, msg, session, "已删除该条记忆 🗑️")
    return _exit_memory(loop, msg, session, "删除失败")


async def _handle_memory_list_selection(
    loop: Any,
    msg: Any,
    session: Any,
    text: str,
    entries: list[dict[str, str]],
) -> Any:
    if text == "0":
        session.metadata["_pending_memory_delete"] = True
        session.metadata.pop("_pending_memory_list", None)
        loop.sessions.save(session)
        return loop._reply(msg, "输入要删除的编号（空格分隔可批量删），输入其他退出")
    if not text.isdigit():
        return _exit_memory(loop, msg, session, "已退出记忆管理 👌")
    index = int(text)
    if not (0 < index <= len(entries)):
        return _exit_memory(loop, msg, session, "无效编号，已退出记忆管理")
    entry = entries[index - 1]
    category = entry.get("category", "general")
    content = entry.get("content", "")
    session.metadata["_pending_memory_detail"] = True
    session.metadata["_memory_selected_index"] = index
    session.metadata.pop("_pending_memory_list", None)
    loop.sessions.save(session)
    return loop._reply(
        msg,
        f"🧠 [{category}] 记忆详情:\n\n{content}\n\n输入 9 编辑，输入 0 删除，其他返回列表",
    )


def _exit_memory(loop: Any, msg: Any, session: Any, text: str) -> Any:
    loop._clear_memory_state(session)
    loop.sessions.save(session)
    return loop._reply(msg, text)
