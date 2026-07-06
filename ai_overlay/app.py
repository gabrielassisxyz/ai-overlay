"""Textual TUI for ai-overlay (docs/spec.md §5) — the Milestone B surface.

A thin UI over the Milestone A core: on mount it captures per the active profile and
streams the answer; typed text continues the *same* conversation (no re-capture);
``/profile`` lists or switches the active profile for subsequent asks. Every blocking
seam (``capture``, the LLM client) is injected so :meth:`App.run_test` drives it
offline, mirroring how ``__main__`` injects them for the headless path.

Rendering decision (no silent decisions): each assistant turn accumulates its streamed
deltas into a single ``Markdown`` widget that is re-rendered as the text grows. This is
the simplest path and good enough for MVP; if it ever proves too heavy we'd stream into
a plain ``Static`` and render Markdown once per completed turn (spec §5 note).

Threading decision: ``capture`` and ``stream_reply`` block, so a turn runs on a Textual
thread worker (``@work(thread=True)``) and hands each delta back to the UI via
``call_from_thread``. Never call these on the event loop or the UI freezes.
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
from ai_overlay.llm import LLMError, build_messages, stream_reply

# The injected capture: ``(mode, *, max_width) -> PNG bytes``. Same shape as
# ``ai_overlay.capture.capture`` with the ``run`` seam bound, so tests pass a fake.
CaptureFn = Callable[..., bytes]


class OverlayApp(App):
    """The summon → capture → stream → follow-up popup."""

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
    BINDINGS = [
        Binding("escape", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True),
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
        # The in-memory conversation; grows each turn, lives only for this popup.
        self.messages: list[dict] = []

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="transcript")
        yield Input(placeholder="Ask a follow-up, or /profile …", id="prompt")

    def on_mount(self) -> None:
        self.query_one("#prompt", Input).focus()
        label = self.initial_question or "(asking about the captured screen)"
        self._add_label(f"you [{self.active_profile.name}]: {label}")
        self._start_turn(capture_first=True)

    # --- input handling -----------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if text.startswith("/"):
            self._handle_command(text[1:])
            return
        # Plain text continues the same conversation — a follow-up never re-captures.
        self.messages.append({"role": "user", "content": text})
        self._add_label(f"you: {text}")
        self._start_turn(capture_first=False)

    def _handle_command(self, raw: str) -> None:
        """Only ``/profile`` exists (spec §5) — this is not a command framework."""
        parts = raw.split()
        command = parts[0] if parts else ""
        if command != "profile":
            self._add_error(
                f"Unknown command /{command or ''}. The only command is /profile."
            )
            return
        if len(parts) == 1:
            self._list_profiles()
        else:
            self._switch_profile(parts[1])

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
        # Switch affects subsequent asks only: history is not rewritten and nothing is
        # re-captured (spec §5). The next ask uses this profile's model.
        self.active_profile = profile
        self._add_label(f"switched to profile {name!r} (applies to the next ask).")

    # --- turn lifecycle -----------------------------------------------------

    def _start_turn(self, *, capture_first: bool) -> None:
        self.query_one("#prompt", Input).disabled = True
        self._run_turn(capture_first)

    @work(thread=True)
    def _run_turn(self, capture_first: bool) -> None:
        """Run the blocking capture + stream off the UI thread (docs/spec.md §5)."""
        try:
            if capture_first:
                system_prompt = self.active_profile.read_system_prompt()
                image = self._capture(
                    self.active_profile.capture, max_width=self.config.max_image_width
                )
                self.messages = build_messages(
                    system_prompt, self.initial_question, image
                )
            answer = self.call_from_thread(self._begin_assistant)
            full = ""
            for delta in stream_reply(
                self._client, self.active_profile.model, self.messages
            ):
                full += delta
                self.call_from_thread(answer.update, full)
            self.messages.append({"role": "assistant", "content": full})
        except (ConfigError, CaptureError, LLMError) as err:
            self.call_from_thread(self._add_error, str(err))
        finally:
            self.call_from_thread(self._end_turn)

    async def _begin_assistant(self) -> Markdown:
        """Mount (and await) the assistant's Markdown widget, then return it to fill."""
        answer = Markdown()
        transcript = self.query_one("#transcript", VerticalScroll)
        await transcript.mount(answer)
        transcript.scroll_end(animate=False)
        return answer

    def _end_turn(self) -> None:
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
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
