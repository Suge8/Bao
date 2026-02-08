import builtins

import nanobot.cli.commands as commands


def test_read_interactive_input_uses_plain_input(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_print(*args, **kwargs):
        captured["printed"] = args
        captured["print_kwargs"] = kwargs

    def fake_input(prompt: str = "") -> str:
        captured["prompt"] = prompt
        return "hello"

    monkeypatch.setattr(commands.console, "print", fake_print)
    monkeypatch.setattr(builtins, "input", fake_input)

    value = commands._read_interactive_input()

    assert value == "hello"
    assert captured["prompt"] == ""
    assert captured["print_kwargs"] == {"end": ""}
    assert captured["printed"] == ("[bold blue]You:[/bold blue] ",)


def test_flush_pending_tty_input_skips_non_tty(monkeypatch) -> None:
    class FakeStdin:
        def fileno(self) -> int:
            return 0

    monkeypatch.setattr(commands.sys, "stdin", FakeStdin())
    monkeypatch.setattr(commands.os, "isatty", lambda _fd: False)

    commands._flush_pending_tty_input()

