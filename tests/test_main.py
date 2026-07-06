"""Wiring tests for the headless (``--print``) entrypoint (docs/spec.md §6-A).

config/capture/llm are exercised for real elsewhere; here we only check the
orchestration: real config + prompt file, faked capture + LLM, output to a buffer.
The TUI is the default now, so these exercise the ``--print`` one-shot path.
"""

from __future__ import annotations

import io

import pytest

from ai_overlay import __main__ as entry
from ai_overlay.capture import CaptureError


@pytest.fixture
def config_file(tmp_path):
    prompt = tmp_path / "generic.md"
    prompt.write_text("You are helpful.", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
        default_profile = "generic"
        [profiles.generic]
        system_prompt_file = "{prompt}"
        """,
        encoding="utf-8",
    )
    return config


def test_run_streams_answer_to_out(config_file, monkeypatch):
    calls = {}

    def fake_capture(mode, *, max_width):
        calls["capture"] = (mode, max_width)
        return b"png-bytes"

    def fake_stream(client, model, messages):
        calls["stream"] = (model, messages)
        yield "Hello "
        yield "world"

    monkeypatch.setattr(entry, "capture", fake_capture)
    monkeypatch.setattr(entry, "make_client", lambda base_url, api_key: "client")
    monkeypatch.setattr(entry, "stream_reply", fake_stream)

    out = io.StringIO()
    code = entry.run(
        ["--print", "--config", str(config_file), "which", "item?"], out=out
    )

    assert code == 0
    assert out.getvalue() == "Hello world\n"
    assert calls["capture"] == ("fullscreen", 1280)
    model, messages = calls["stream"]
    assert model == "kimi-k2.7"
    assert messages[0]["content"] == "You are helpful."
    # the trailing question words are joined into the user text
    assert messages[1]["content"][0] == {"type": "text", "text": "which item?"}


def test_run_reports_capture_error(config_file, monkeypatch, capsys):
    def boom(mode, *, max_width):
        raise CaptureError("grim not found")

    monkeypatch.setattr(entry, "capture", boom)

    code = entry.run(["--print", "--config", str(config_file)], out=io.StringIO())

    assert code == 1
    assert "grim not found" in capsys.readouterr().err


def test_run_reports_unknown_profile(config_file, capsys):
    code = entry.run(
        ["--config", str(config_file), "--profile", "ghost"], out=io.StringIO()
    )
    assert code == 1
    assert "ghost" in capsys.readouterr().err
