from bao.command_text import (
    build_help_text,
    extract_command_name,
    iter_telegram_command_specs,
    iter_telegram_forward_command_names,
)


def test_help_text_lists_memory_command() -> None:
    help_text = build_help_text()

    assert "/memory — Manage long-term memory" in help_text
    assert "/model — Switch model" in help_text


def test_extract_command_name_recognizes_model_with_args() -> None:
    assert extract_command_name("/model openai/gpt-5") == "model"
    assert extract_command_name("/memory") == "memory"
    assert extract_command_name("hello") is None
    assert extract_command_name("/unknown") is None


def test_telegram_command_projection_comes_from_core_registry() -> None:
    menu_names = [spec.name for spec in iter_telegram_command_specs()]
    forwarded_names = list(iter_telegram_forward_command_names())

    assert menu_names[0] == "start"
    assert menu_names[-1] == "help"
    assert "start" not in forwarded_names
    assert "memory" in menu_names
    assert "model" in menu_names
    assert "memory" in forwarded_names
