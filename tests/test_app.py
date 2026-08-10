"""Pilot tests for the Textual TUI (docs/spec.md §5, §6-B).

Everything runs offline: a fake ``capture`` returns fixed PNG bytes and a fake LLM
client (same shape as ``tests/test_llm.py``) yields deltas. We drive the app with
``App.run_test`` and wait for the thread worker between turns.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from openai import OpenAIError
from textual.widgets import Input, Markdown, Static

from ai_overlay.app import OverlayApp
from ai_overlay.config import load_config


def _chunk(content: str | None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
    )


class FakeClient:
    """Records each create()'s model + messages and replays deltas (or raises)."""

    def __init__(self, deltas=None, error: Exception | None = None):
        self.calls: list[list[dict]] = []
        self.models: list[str] = []
        self._deltas = deltas or ["Hello", " world"]
        self._error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, messages, stream):
        self.calls.append(messages)
        self.models.append(model)
        if self._error is not None:
            raise self._error
        return iter(_chunk(d) for d in self._deltas)


def _write_config(tmp_path, *, auto_capture=True):
    """A config with two profiles so /profile switching has somewhere to go."""
    (tmp_path / "generic.md").write_text("You are helpful.", encoding="utf-8")
    (tmp_path / "deck.md").write_text("You advise on decks.", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
        default_profile = "generic"
        auto_capture = {str(auto_capture).lower()}
        [profiles.generic]
        system_prompt_file = "{tmp_path / "generic.md"}"
        [profiles.deck]
        system_prompt_file = "{tmp_path / "deck.md"}"
        model = "deck-model"
        """,
        encoding="utf-8",
    )
    return load_config(config)


def _make_app(tmp_path, *, client, question="what is this?", auto_capture=True):
    config = _write_config(tmp_path, auto_capture=auto_capture)
    calls = {"captures": []}

    def fake_capture(mode, *, max_width):
        calls["captures"].append((mode, max_width))
        return b"png-bytes"

    app = OverlayApp(
        config,
        config.resolve(None),
        capture=fake_capture,
        client=client,
        initial_question=question,
    )
    return app, calls


def _statics_text(app) -> str:
    return "\n".join(str(w.render()) for w in app.query(Static))


def _turn_text(turn: dict) -> str:
    """Extract the text of a user turn (content is a list of typed parts)."""
    return " ".join(p["text"] for p in turn["content"] if p.get("type") == "text")


def test_launch_auto_captures_and_streams(tmp_path):
    client = FakeClient(deltas=["Hel", "lo"])

    async def scenario():
        app, calls = _make_app(tmp_path, client=client)
        async with app.run_test():
            await app.workers.wait_for_complete()
            assert calls["captures"] == [("fullscreen", 1280)]
            # The first request leads with the active profile's system prompt + image.
            first = client.calls[0]
            assert first[0] == {"role": "system", "content": "You are helpful."}
            assert app.history[-1] == {"role": "assistant", "content": "Hello"}
            assert any(w.source == "Hello" for w in app.query(Markdown))

    asyncio.run(scenario())


def test_follow_up_continues_without_recapture(tmp_path):
    client = FakeClient(deltas=["ok"])

    async def scenario():
        app, calls = _make_app(tmp_path, client=client)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()

            app.query_one("#prompt", Input).value = "and now?"
            await pilot.press("enter")
            await app.workers.wait_for_complete()

            # A plain follow-up never re-captures (only the launch shot was taken).
            assert calls["captures"] == [("fullscreen", 1280)]
            assert _turn_text(app.history[-2]) == "and now?"
            assert app.history[-1] == {"role": "assistant", "content": "ok"}
            assert len(client.calls) == 2

    asyncio.run(scenario())


def test_capture_command_stages_a_shot_sent_with_next_message(tmp_path):
    client = FakeClient(deltas=["done"])

    async def scenario():
        # auto_capture off: the overlay opens idle and we drive capture by hand.
        app, calls = _make_app(tmp_path, client=client, auto_capture=False)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            assert calls["captures"] == []  # nothing captured on launch
            assert client.calls == []  # nothing sent on launch

            app.query_one("#prompt", Input).value = "/capture"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            assert app.pending_image == b"png-bytes"
            assert "attached" in _statics_text(app)

            app.query_one("#prompt", Input).value = "what to pick?"
            await pilot.press("enter")
            await app.workers.wait_for_complete()

            # Exactly one capture, and the message carried both text and the image.
            assert calls["captures"] == [("fullscreen", 1280)]
            sent = client.calls[0][-1]
            assert _turn_text(sent) == "what to pick?"
            assert any(p.get("type") == "image_url" for p in sent["content"])
            assert app.pending_image is None  # consumed by the send

    asyncio.run(scenario())


def test_profile_switch_hot_reloads_prompt_and_model(tmp_path):
    client = FakeClient(deltas=["x"])

    async def scenario():
        app, _ = _make_app(tmp_path, client=client)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()  # first turn under 'generic'
            assert client.models[0] == "kimi-k2.7"

            app.query_one("#prompt", Input).value = "/profile deck"
            await pilot.press("enter")
            await pilot.pause()
            assert app.active_profile.name == "deck"

            app.query_one("#prompt", Input).value = "go"
            await pilot.press("enter")
            await app.workers.wait_for_complete()

            # The next send rebuilds the system message from 'deck' and uses its model.
            second = client.calls[1]
            assert second[0] == {"role": "system", "content": "You advise on decks."}
            assert client.models[1] == "deck-model"
            # The transition note (mitigation B) is prepended to that message.
            assert "switched to profile 'deck'" in _turn_text(second[-1])
            assert "go" in _turn_text(second[-1])

    asyncio.run(scenario())


def test_profile_list_marks_the_active_one(tmp_path):
    async def scenario():
        app, _ = _make_app(tmp_path, client=FakeClient())
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()

            app.query_one("#prompt", Input).value = "/profile"
            await pilot.press("enter")
            await pilot.pause()

            text = _statics_text(app)
            assert "* generic" in text
            assert "  deck" in text

    asyncio.run(scenario())


def test_llm_error_surfaces_without_crashing(tmp_path):
    client = FakeClient(error=OpenAIError("connection refused"))

    async def scenario():
        app, _ = _make_app(tmp_path, client=client)
        async with app.run_test():
            await app.workers.wait_for_complete()

            assert "error:" in _statics_text(app)
            # The cause reaches the pane, not just the fact that something failed.
            assert "connection refused" in _statics_text(app)
            # No assistant turn recorded, and the input is usable again.
            assert not any(m.get("role") == "assistant" for m in app.history)
            assert app.query_one("#prompt", Input).disabled is False

    asyncio.run(scenario())


def test_escape_quits(tmp_path):
    async def scenario():
        app, _ = _make_app(tmp_path, client=FakeClient())
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("escape")
            await pilot.pause()
            assert app._exit is True

    asyncio.run(scenario())


def test_screenshot_hotkey_stages_a_shot_like_capture(tmp_path):
    """F2 stages a screenshot without typing /capture (Milestone C, spec §5/§7)."""
    client = FakeClient(deltas=["done"])

    async def scenario():
        # auto_capture off so the launch takes no shot — the hotkey is the only capture.
        app, calls = _make_app(tmp_path, client=client, auto_capture=False)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            assert calls["captures"] == []

            await pilot.press("f2")
            await app.workers.wait_for_complete()
            assert calls["captures"] == [("fullscreen", 1280)]
            assert app.pending_image == b"png-bytes"
            assert "attached" in _statics_text(app)

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["active-window", "region"])
def test_launch_honors_the_profile_capture_mode(tmp_path, mode):
    """The TUI passes the active profile's mode straight to capture — so active-window
    and region are exercised end-to-end, not just at the capture unit (Milestone C)."""
    (tmp_path / "p.md").write_text("prompt", encoding="utf-8")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
        default_profile = "p"
        [profiles.p]
        system_prompt_file = "{tmp_path / "p.md"}"
        capture = "{mode}"
        """,
        encoding="utf-8",
    )
    config = load_config(config_path)
    captured: list[str] = []

    def fake_capture(m, *, max_width):
        captured.append(m)
        return b"png-bytes"

    app = OverlayApp(
        config,
        config.resolve(None),
        capture=fake_capture,
        client=FakeClient(deltas=["ok"]),
        initial_question=None,
    )

    async def scenario():
        async with app.run_test():
            await app.workers.wait_for_complete()
            assert captured == [mode]

    asyncio.run(scenario())
