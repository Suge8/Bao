from __future__ import annotations

READ_ONLY_ALLOW_PATTERNS: list[str] = [
    r"^\s*(cat|ls|find|grep|head|tail|wc|file|stat|echo|pwd|which|env|printenv|less|more|tree|du|diff|basename|dirname|realpath)\b",
]

READ_ONLY_BLOCK_PATTERNS: list[str] = [
    r"(?:^|[^\\])(>>?|1>|2>|&>)",
    r"\|\s*tee\b",
    r"\b(touch|mkdir|cp|mv|install|ln|truncate)\b",
    r"\b(python|python3|node|ruby|perl|php|lua)\b",
    r"\b(vi|vim|nano|emacs)\b",
]

DEFAULT_DENY_PATTERNS: list[str] = [
    r"\brm\s+-[rf]{1,2}\b",
    r"\bdel\s+/[fq]\b",
    r"\brmdir\s+/s\b",
    r"(?:^|[;&|]\s*)format\b",
    r"\b(mkfs|diskpart)\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd",
    r"\b(shutdown|reboot|poweroff)\b",
    r":\(\)\s*\{.*\};\s*:",
]
