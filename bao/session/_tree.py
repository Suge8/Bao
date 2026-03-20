from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable


def collect_session_tree_keys(
    root_key: str,
    child_keys_for: Callable[[str], Iterable[str]],
) -> list[str]:
    normalized_root = str(root_key or "").strip()
    if not normalized_root:
        return []

    keys = [normalized_root]
    visited = {normalized_root}
    pending = deque([normalized_root])

    while pending:
        current = pending.popleft()
        for child_key in child_keys_for(current):
            normalized_child = str(child_key or "").strip()
            if not normalized_child or normalized_child in visited:
                continue
            visited.add(normalized_child)
            keys.append(normalized_child)
            pending.append(normalized_child)

    return keys
