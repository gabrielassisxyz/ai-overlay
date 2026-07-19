"""Textual TUI for ai-overlay (docs/spec.md §5) — the Milestone B surface.

A thin UI over the Milestone A core. The interaction is an *attachment* model: a
screenshot is staged as a pending attachment and sent together with your message.

- ``auto_capture`` on (default): launch captures + sends immediately (summon-and-ask).
- ``auto_capture`` off: launch opens idle; ``/capture`` stages a shot on demand.
- ``/capture`` (or the ``F2`` hotkey) (re)captures per the active profile's mode and
  stages the image; the next message sends it. A message with no fresh capture is a
  plain follow-up.
- ``/profile <name>`` hot-reloads the active profile: every send rebuilds the payload
  as ``[system(active profile)] + history + turn``, so the new prompt and model take
  effect from the next message, keeping the conversation and the staged image.

The blocking seams (``capture``, the LLM client) are injected so :meth:`App.run_test`
drives it offline, and they run on a Textual thread worker so the UI never freezes;
deltas come back via ``call_from_thread``.

Two decisions kept explicit (no silent calls):
- **Rendering:** each answer accumulates its streamed deltas into one ``Markdown``
  widget re-rendered as it grows — simplest; a Static-then-render fallback is the
  escape hatch if it proves heavy.
- **Profile switch:** history is *not* rewritten, but the leading system message is
  rebuilt from the active profile on every send (hot-reload). A short transition note
  is prepended to the next message so the model has an explicit pivot.
"""

from __future__ import annotations

from collections.abc import Callable

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Input, Markdown, Static

from ai_overlay.capture import CaptureError
from ai_overlay.config import Config, ConfigError, Profile
from ai_overlay.llm import LLMError, build_user_turn, stream_reply

# The injected capture: ``(mode, *, max_width) -> PNG bytes``. Same shape as
# ``ai_overlay.capture.capture`` with the ``run`` seam bound, so tests pass a fake.
CaptureFn = Callable[..., bytes]

_ATTACH_PLACEHOLDER = "Attachment ready — type & send, or Enter to send just the shot…"
_IDLE_PLACEHOLDER = "Message, /capture (or F2) to attach a screenshot, or /profile…"


class OverlayApp(App):
    """The summon → (capture) → stream → follow-up popup."""

    CSS = """
    #transcript {
        height: 1fr;
        padding: 0 1;
    }
    .turn-label {
        color: $text-muted;
        margin: 1 0 0 0;
    }
    .error {
        color: $error;
        margin: 1 0 0 0;
    }
    #prompt {
        dock: bottom;
    }
    """

    # Esc and Ctrl+C both quit (spec §5). Priority so the Input can't swallow Esc.
    # F2 is the screenshot hotkey (spec §5/§7, Milestone C): stage a shot without typing
    # /capture. The Input never consumes F-keys, so a plain (non-priority) binding
    # reaches the app via normal bubbling.
    BINDINGS = [
        Binding("escape", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("f2", "capture", "Screenshot"),
    ]

    def __init__(
        self,
        config: Config,
        profile: Profile,
        *,
        capture: CaptureFn,
        client: object,
        initial_question: str | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.active_profile = profile
        self._capture = capture
        self._client = client
        self.initial_question = initial_question
        # User/assistant turns only; the system message is rebuilt per send (§5).
        self.history: list[dict] = []
        # A screenshot staged by launch or /capture, sent with the next message.
        self.pending_image: bytes | None = None
        # A one-shot marker prepended to the next message after a /profile switch (B).
        self._transition_note: str | None = None

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="transcript")
        yield Input(placeholder=_IDLE_PLACEHOLDER, id="prompt")

    def on_mount(self) -> None:
        self.query_one("#prompt", Input).focus()
        if self.config.auto_capture:
            question = self.initial_question or "(about the current screen)"
            self._add_label(f"you [{self.active_profile.name}]: {question}")
            self._set_busy(True)
            self._worker_turn(self.initial_question or "", capture_first=True)
        else:
            self._add_label(
                "Ready. /capture (or F2) to attach a screenshot, then type & send."
            )

    # --- input handling -----------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if text.startswith("/"):
            self._handle_command(text[1:])
            return
        # Nothing to send: empty text and no staged image.
        if not text and self.pending_image is None:
            return
        shown = text or "(sent the screenshot)"
        if self.pending_image is not None:
            shown += "  📎"
        self._add_label(f"you: {shown}")
        self._set_busy(True)
        self._worker_turn(text, capture_first=False)

    def _handle_command(self, raw: str) -> None:
        """Only ``/profile`` and ``/capture`` exist — not a command framework (§5)."""
        parts = raw.split()
        command = parts[0] if parts else ""
        if command == "capture":
            self._start_capture()
        elif command == "profile" and len(parts) == 1:
            self._list_profiles()
        elif command == "profile":
            self._switch_profile(parts[1])
        else:
            self._add_error(
                f"Unknown command /{command or ''}. Commands: /profile, /capture."
            )

    def action_capture(self) -> None:
        """F2 hotkey: stage a shot like ``/capture`` without typing it (Milestone C)."""
        self._start_capture()

    def _start_capture(self) -> None:
        """Stage a fresh screenshot for the next message. Shared by ``/capture`` and F2.

        Guarded: if a turn or capture is already in flight the input is disabled, so a
        second capture (e.g. the hotkey pressed mid-stream) is ignored, not raced.
        """
        if self.query_one("#prompt", Input).disabled:
            return
        self._set_busy(True)
        self._worker_capture()

    def _list_profiles(self) -> None:
        lines = [
            f"{'* ' if name == self.active_profile.name else '  '}{name}"
            for name in sorted(self.config.profiles)
        ]
        self._add_label("profiles (* = active):\n" + "\n".join(lines))

    def _switch_profile(self, name: str) -> None:
        profile = self.config.profiles.get(name)
        if profile is None:
            available = ", ".join(sorted(self.config.profiles))
            self._add_error(f"Unknown profile {name!r}. Available: {available}.")
            return
        # Hot-reload: the switch keeps past turns, but every send rebuilds the system
        # message from the active profile, so the new prompt/model apply next (§5).
        self.active_profile = profile
        # A transition note (mitigation B) gives the model an explicit pivot for the
        # already-written turns; it is prepended to the next message only if there's
        # history to reconcile.
        if self.history:
            self._transition_note = f"[switched to profile '{name}']"
        self._add_label(
            f"switched to profile {name!r} — applies from your next message."
        )

    # --- turn lifecycle -----------------------------------------------------

    @work(thread=True)
    def _worker_turn(self, text: str, capture_first: bool) -> None:
        """Capture (optionally), then send + stream — all off the UI thread (§5)."""
        try:
            if capture_first:
                image = self._capture(
                    self.active_profile.capture, max_width=self.config.max_image_width
                )
                self.call_from_thread(self._stage_image, image, announce=False)
            self._send(text)
        except (ConfigError, CaptureError, LLMError) as err:
            self.call_from_thread(self._add_error, str(err))
        finally:
            self.call_from_thread(self._set_busy, False)

    @work(thread=True)
    def _worker_capture(self) -> None:
        """Stage a fresh screenshot for the next message (capture blocks, off-UI)."""
        try:
            image = self._capture(
                self.active_profile.capture, max_width=self.config.max_image_width
            )
            self.call_from_thread(self._stage_image, image, announce=True)
        except CaptureError as err:
            self.call_from_thread(self._add_error, str(err))
        finally:
            self.call_from_thread(self._set_busy, False)

    def _send(self, text: str) -> None:
        """Assemble ``[system] + history + turn`` and stream the reply (in-thread)."""
        system_prompt = self.active_profile.read_system_prompt()
        note = self._transition_note
        self._transition_note = None
        outgoing = f"{note}\n{text}".strip() if note else text
        self.history.append(build_user_turn(outgoing or None, self.pending_image))
        self.pending_image = None
        messages = [{"role": "system", "content": system_prompt}, *self.history]

        answer = self.call_from_thread(self._begin_assistant)
        full = ""
        for delta in stream_reply(self._client, self.active_profile.model, messages):
            full += delta
            self.call_from_thread(answer.update, full)
        self.history.append({"role": "assistant", "content": full})

    async def _begin_assistant(self) -> Markdown:
        """Mount (and await) the assistant's Markdown widget, then return it to fill."""
        answer = Markdown()
        transcript = self.query_one("#transcript", VerticalScroll)
        await transcript.mount(answer)
        transcript.scroll_end(animate=False)
        return answer

    def _stage_image(self, image: bytes, *, announce: bool) -> None:
        self.pending_image = image
        if announce:
            self._add_label("📎 screenshot attached (sent with your next message).")

    def _set_busy(self, busy: bool) -> None:
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = busy
        if not busy:
            prompt.placeholder = (
                _ATTACH_PLACEHOLDER if self.pending_image else _IDLE_PLACEHOLDER
            )
            prompt.focus()
            self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)

    # --- transcript helpers -------------------------------------------------

    def _add_label(self, text: str) -> None:
        self._mount_line(Static(text, classes="turn-label"))

    def _add_error(self, text: str) -> None:
        self._mount_line(Static(f"error: {text}", classes="error"))

    def _mount_line(self, widget: Static) -> None:
        transcript = self.query_one("#transcript", VerticalScroll)
        transcript.mount(widget)
        transcript.scroll_end(animate=False)
