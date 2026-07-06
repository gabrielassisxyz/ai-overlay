"""Entrypoint: launch the Textual TUI, or run one headless shot with ``--print``.

The TUI (Milestone B) is the default: `python -m ai_overlay [--profile NAME] [question]`
summons the popup, captures per the active profile, and streams the answer with
in-session follow-ups. The Milestone A stdout path stays available behind ``--print``
for scripting and quick debugging without a TTY.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from ai_overlay.app import OverlayApp
from ai_overlay.capture import CaptureError, capture
from ai_overlay.config import Config, ConfigError, Profile, load_config, resolve_api_key
from ai_overlay.llm import LLMError, build_messages, make_client, stream_reply

DEFAULT_CONFIG_PATH = Path("~/.config/ai-overlay/config.toml").expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-overlay",
        description="Capture the screen and ask the LLM about it via LiteLLM.",
    )
    parser.add_argument(
        "--profile", default=None, help="Profile name (default: config's)."
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to config.toml."
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_headless",
        help="One-shot: stream the answer to stdout instead of launching the TUI.",
    )
    parser.add_argument("question", nargs="*", help="Optional initial question.")
    return parser


def run(argv: Sequence[str] | None = None, *, out: TextIO = sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        profile = config.resolve(args.profile)
        question = " ".join(args.question) or None
        if args.print_headless:
            return _run_headless(config, profile, question, out=out)
        return _launch_tui(config, profile, question)
    except (ConfigError, CaptureError, LLMError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


def _run_headless(
    config: Config, profile: Profile, question: str | None, *, out: TextIO
) -> int:
    """Milestone A path: capture once, stream to stdout, done (no TUI)."""
    system_prompt = profile.read_system_prompt()
    image = capture(profile.capture, max_width=config.max_image_width)
    messages = build_messages(system_prompt, question, image)
    client = make_client(config.base_url, resolve_api_key(config))
    for delta in stream_reply(client, profile.model, messages):
        out.write(delta)
        out.flush()
    out.write("\n")
    return 0


def _launch_tui(config: Config, profile: Profile, question: str | None) -> int:
    """Launch the TUI. Capture/LLM failures surface inside the app, not as exit codes.

    Only pre-launch config errors propagate to ``run``'s error handler.
    """
    client = make_client(config.base_url, resolve_api_key(config))
    app = OverlayApp(
        config, profile, capture=capture, client=client, initial_question=question
    )
    app.run()
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
