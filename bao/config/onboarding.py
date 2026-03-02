import importlib.resources
from pathlib import Path


def _read_workspace_template(filename: str, lang: str = "zh") -> str:
    """Read a template from bao/templates/workspace/{lang}/ via importlib.resources."""
    return (
        importlib.resources.files("bao.templates.workspace")
        .joinpath(lang)
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


LANG_PICKER = "嗨 👋 请选择语言 / Pick your language:\n\n1. 中文\n2. English"
PERSONA_GREETING: dict[str, str] = {
    "zh": (
        "嘿 👋 我是运行在 Bao 框架里的 AI 搭子，还没名字呢～\n\n"
        "正式开工之前，先对个暗号：\n\n"
        "1. 给我起个名字呗？\n"
        "2. 你叫啥？怎么称呼你舒服怎么来～\n"
        "3. 平时聊天习惯？随意唠 / 说重点 / 正经点\n\n"
        "4. 一般喜欢做啥？想我以后帮你什么？\n\n"
    ),
    "en": (
        "Hey 👋 I'm ur AI buddy running on the Bao framework — still unnamed tho~\n\n"
        "Before we get rolling, quick intro:\n\n"
        "1. Wanna give me a name?\n"
        "2. What do I call you? Whatever feels right~\n"
        "3. How do you like to chat? Chill / straight to the point / keep it professional\n\n"
        "4. What do you usually like to do? What do you want me to help you with in the future?\n\n"
    ),
}


def detect_onboarding_stage(workspace: Path) -> str:
    """Detect onboarding stage from file existence.
    Returns:
        'lang_select'  — no INSTRUCTIONS.md yet
        'persona_setup' — has INSTRUCTIONS.md but no PERSONA.md
        'ready'        — both files exist
    """
    if not (workspace / "INSTRUCTIONS.md").exists():
        return "lang_select"
    if not (workspace / "PERSONA.md").exists():
        return "persona_setup"
    return "ready"


def infer_language(workspace: Path) -> str:
    """Infer language from INSTRUCTIONS.md first line. Defaults to 'zh'."""
    inst = workspace / "INSTRUCTIONS.md"
    if not inst.exists():
        return "zh"
    first_line = inst.read_text(encoding="utf-8").split("\n", 1)[0]
    return "en" if first_line.strip().lower().startswith("# instructions") else "zh"


def write_instructions(workspace: Path, lang: str) -> None:
    """Write INSTRUCTIONS.md in the chosen language (deferred until onboarding)."""
    tpl = _read_workspace_template("INSTRUCTIONS.md", lang)
    (workspace / "INSTRUCTIONS.md").write_text(tpl, encoding="utf-8")


def write_heartbeat(workspace: Path, lang: str) -> None:
    """Write HEARTBEAT.md in the chosen language (deferred until onboarding)."""
    tpl = _read_workspace_template("HEARTBEAT.md", lang)
    hp = workspace / "HEARTBEAT.md"
    if not hp.exists():
        hp.write_text(tpl, encoding="utf-8")


def write_persona_profile(workspace: Path, lang: str, profile: dict[str, str]) -> None:
    """Write extracted user profile into PERSONA.md, replacing template placeholders."""
    persona = workspace / "PERSONA.md"
    base = _read_workspace_template("PERSONA.md", lang)
    content = base
    user_name = profile.get("user_name", "")
    style = profile.get("style", "")
    role = profile.get("role", "")
    interests = profile.get("interests", "")
    nickname = profile.get("user_nickname", "")
    bot_name = profile.get("bot_name", "")

    if lang == "zh":
        replacements = {
            "（你的名字）": user_name,
            "（随意/正式）": style,
            "（你的角色，如开发者、研究员）": role,
            "（你关注的话题）": interests,
        }
    else:
        replacements = {
            "(your name)": user_name,
            "(casual/formal)": style,
            "(your role, e.g. developer, researcher)": role,
            "(topics you care about)": interests,
        }
    for old, new in replacements.items():
        if new:
            content = content.replace(old, new)
    if bot_name:
        if lang == "zh":
            content = content.replace(
                "我是运行在 Bao 框架里的一个轻量级全能 AGENT。",
                f"我是{bot_name}，运行在 Bao 框架里的一个轻量级全能 AGENT。",
            )
        else:
            content = content.replace(
                "I am Bao, a lightweight AI assistant.",
                f"I am {bot_name}, a lightweight AI assistant.",
            )
    if nickname and nickname != user_name:
        name_val = user_name
        if lang == "zh":
            content = content.replace(
                f"- **姓名**：{name_val}",
                f"- **姓名**：{name_val}（称呼：{nickname}）",
            )
        else:
            content = content.replace(
                f"- **Name**: {name_val}",
                f"- **Name**: {name_val} (call me: {nickname})",
            )
    persona.write_text(content, encoding="utf-8")
