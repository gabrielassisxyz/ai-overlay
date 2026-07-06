"""Pilot tests for the Textual TUI (docs/spec.md §5, §6-B).

Everything runs offline: a fake ``capture`` returns fixed PNG bytes and a fake LLM
client (same shape as ``tests/test_llm.py``) yields deltas. We drive the app with
``App.run_test`` and wait for the thread worker between turns.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from openai import OpenAIError
from textual.widgets import Input, Markdown, Static

from ai_overlay.app import OverlayApp
from ai_overlay.config import load_config


def _chunk(content: str | None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
    )


class FakeClient:
    """Records each create()'s messages and replays canned deltas (or raises)."""

    def __init__(self, deltas=None, error: Exception | None = None):
        self.calls: list[list[dict]] = []
        self._deltas = deltas or ["Hello", " world"]
        self._error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, messages, stream):
        self.calls.append(messages)
        if self._error is not None:
            raise self._error
        return iter(_chunk(d) for d in self._deltas)


def _write_config(tmp_path):
    """A config with two profiles so /profile switching has somewhere to go."""
    (tmp_path / "generic.md").write_text("You are helpful.", encoding="utf-8")
    (tmp_path / "deck.md").write_text("You advise on decks.", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
        default_profile = "generic"
        [profiles.generic]
        system_prompt_file = "{tmp_path / "generic.md"}"
        [profiles.deck]
        system_prompt_file = "{tmp_path / "deck.md"}"
        model = "deck-model"
        """,
        encoding="utf-8",
    )
    return load_config(config)


def _make_app(tmp_path, *, client, question="what is this?"):
    config = _write_config(tmp_path)
    calls = {}

    def fake_capture(mode, *, max_width):
        calls["capture"] = (mode, max_width)
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


def test_first_turn_captures_and_streams(tmp_path):
    client = FakeClient(deltas=["Hel", "lo"])

    async def scenario():
        app, calls = _make_app(tmp_path, client=client)
        async with app.run_test():
            await app.workers.wait_for_complete()
            assert calls["capture"] == ("fullscreen", 1280)
            # The first request carries the system prompt + the captured image.
            first = client.calls[0]
            assert first[0] == {"role": "system", "content": "You are helpful."}
            assert app.messages[-1] == {"role": "assistant", "content": "Hello"}
            assert any(w.source == "Hello" for w in app.query(Markdown))

    asyncio.run(scenario())


def test_follow_up_continues_conversation_without_recapture(tmp_path):
    client = FakeClient(deltas=["ok"])

    async def scenario():
        app, calls = _make_app(tmp_path, client=client)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            calls.pop("capture")  # forget the first-turn capture

            app.query_one("#prompt", Input).value = "and now?"
            await pilot.press("enter")
            await app.workers.wait_for_complete()

            # A follow-up never re-captures (spec §5).
            assert "capture" not in calls
            # It appends to the same conversation and streams a fresh answer.
            assert {"role": "user", "content": "and now?"} in app.messages
            assert app.messages[-1] == {"role": "assistant", "content": "ok"}
            # The second request replays the growing history (2 turns so far).
            assert len(client.calls) == 2
            assert {"role": "user", "content": "and now?"} in client.calls[1]

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


def test_profile_switch_changes_model_for_next_ask(tmp_path):
    client = FakeClient(deltas=["done"])

    async def scenario():
        app, _ = _make_app(tmp_path, client=client)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()

            app.query_one("#prompt", Input).value = "/profile deck"
            await pilot.press("enter")
            await pilot.pause()
            assert app.active_profile.name == "deck"

            # The switch does not rewrite history nor re-capture; it changes the model
            # for the next ask. Verify by streaming a follow-up under the new profile.
            captured: list[str] = []

            def create(*, model, messages, stream):
                captured.append(model)
                return iter([])

            client.chat.completions.create = create
            app.query_one("#prompt", Input).value = "go"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            assert captured == ["deck-model"]

    asyncio.run(scenario())


def test_llm_error_surfaces_without_crashing(tmp_path):
    client = FakeClient(error=OpenAIError("connection refused"))

    async def scenario():
        app, _ = _make_app(tmp_path, client=client)
        async with app.run_test():
            await app.workers.wait_for_complete()

            assert "error:" in _statics_text(app)
            assert "LiteLLM proxy" in _statics_text(app)
            # No assistant turn was recorded, and the input is usable again.
            assert not any(m.get("role") == "assistant" for m in app.messages)
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
