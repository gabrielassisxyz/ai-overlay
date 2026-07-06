"""Milestone A entrypoint: capture -> proxy -> stream the answer to stdout.

No TUI yet (that is Milestone B). This is the "validate the idea end-to-end" path:
`python -m ai_overlay [--profile NAME] [question...]`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from ai_overlay.capture import CaptureError, capture
from ai_overlay.config import ConfigError, load_config, resolve_api_key
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
    parser.add_argument("question", nargs="*", help="Optional initial question.")
    return parser


def run(argv: Sequence[str] | None = None, *, out: TextIO = sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        profile = config.resolve(args.profile)
        system_prompt = profile.read_system_prompt()
        image = capture(profile.capture, max_width=config.max_image_width)
        question = " ".join(args.question) or None
        messages = build_messages(system_prompt, question, image)
        client = make_client(config.base_url, resolve_api_key(config))
        for delta in stream_reply(client, profile.model, messages):
            out.write(delta)
            out.flush()
        out.write("\n")
    except (ConfigError, CaptureError, LLMError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
