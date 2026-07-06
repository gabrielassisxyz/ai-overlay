"""Talk to the LLM through the local LiteLLM proxy (docs/spec.md §4).

One OpenAI-compatible client, pointed only at the configured ``base_url`` (localhost).
The client is injected into :func:`stream_reply` so tests never hit the network. A
failed call is re-raised as :class:`LLMError` with an actionable message rather than a
swallowed traceback.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator

from openai import OpenAI, OpenAIError


class LLMError(Exception):
    """The proxy was unreachable or the completion call failed."""


def make_client(base_url: str, api_key: str) -> OpenAI:
    """Build the OpenAI-compatible client. ``api_key`` comes from the env (spec §2)."""
    return OpenAI(base_url=base_url, api_key=api_key)


def build_user_turn(text: str | None, image_png: bytes | None) -> dict:
    """One ``user`` turn: optional text plus an optional base64 image attachment.

    The TUI assembles a payload as ``[system] + history + this turn`` so the *current*
    profile's system prompt leads every call (hot-reload on ``/profile`` switch).
    """
    content: list[dict] = []
    if text:
        content.append({"type": "text", "text": text})
    if image_png is not None:
        encoded = base64.b64encode(image_png).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded}"},
            }
        )
    return {"role": "user", "content": content}


def build_messages(
    system_prompt: str,
    user_text: str | None,
    image_png: bytes | None,
) -> list[dict]:
    """Assemble a one-shot chat payload: system prompt + a single user turn."""
    return [
        {"role": "system", "content": system_prompt},
        build_user_turn(user_text, image_png),
    ]


def stream_reply(client: OpenAI, model: str, messages: list[dict]) -> Iterator[str]:
    """Yield the reply's text deltas as they stream in from the proxy."""
    try:
        stream = client.chat.completions.create(
            model=model, messages=messages, stream=True
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except OpenAIError as err:
        raise LLMError(
            f"LLM call failed. Is the LiteLLM proxy running on localhost:4000? ({err})"
        ) from err
