"""Tests for the LLM message payload and streaming (docs/spec.md §4).

A fake client stands in for the OpenAI-compatible client: no network is touched, and
we assert both the request shape and the streamed deltas.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, OpenAIError

from ai_overlay import llm

_REQUEST = httpx.Request("POST", "http://localhost:4000/v1/chat/completions")


def _status_error(status: int, message: str) -> APIStatusError:
    """An error the endpoint *answered* with, as opposed to one reaching it."""
    return APIStatusError(
        message, response=httpx.Response(status, request=_REQUEST), body=None
    )


def _chunk(content: str | None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
    )


class FakeClient:
    """Records the create() kwargs and replays canned chunks (or raises)."""

    def __init__(
        self,
        chunks=None,
        error: Exception | None = None,
        base_url: str = "http://localhost:4000/v1",
    ):
        self.create_kwargs: dict | None = None
        self.base_url = base_url
        self._chunks = chunks or []
        self._error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.create_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return iter(self._chunks)


def test_build_messages_with_text_and_image():
    messages = llm.build_messages("You are helpful.", "What is this?", b"\x89PNGdata")

    assert messages[0] == {"role": "system", "content": "You are helpful."}
    content = messages[1]["content"]
    assert content[0] == {"type": "text", "text": "What is this?"}

    image = content[1]
    expected = base64.b64encode(b"\x89PNGdata").decode()
    assert image["type"] == "image_url"
    assert image["image_url"]["url"] == f"data:image/png;base64,{expected}"


def test_build_messages_image_only_when_no_text():
    content = llm.build_messages("sys", None, b"img")[1]["content"]
    assert len(content) == 1
    assert content[0]["type"] == "image_url"


def test_build_messages_text_only_when_no_image():
    content = llm.build_messages("sys", "just text", None)[1]["content"]
    assert content == [{"type": "text", "text": "just text"}]


def test_stream_reply_joins_deltas_and_skips_empty():
    client = FakeClient(chunks=[_chunk("Hello"), _chunk(None), _chunk(" world")])

    out = "".join(
        llm.stream_reply(client, "kimi-k2.7", [{"role": "user", "content": "x"}])
    )

    assert out == "Hello world"
    assert client.create_kwargs["model"] == "kimi-k2.7"
    assert client.create_kwargs["stream"] is True


def test_unreachable_endpoint_names_the_configured_url_not_a_hardcoded_one():
    """A user who moved `base_url` must be sent to the endpoint they configured."""
    client = FakeClient(
        error=APIConnectionError(request=_REQUEST), base_url="http://localhost:9999/v1"
    )

    with pytest.raises(llm.LLMError) as caught:
        list(llm.stream_reply(client, "kimi-k2.7", []))

    assert "http://localhost:9999/v1" in str(caught.value)
    assert "4000" not in str(caught.value)


def test_rejected_call_reports_the_endpoints_answer_not_a_reachability_guess():
    """The commonest stranger failure: a live endpoint that lacks the model."""
    client = FakeClient(error=_status_error(404, "model kimi-k2.7 not found"))

    with pytest.raises(llm.LLMError) as caught:
        list(llm.stream_reply(client, "kimi-k2.7", []))

    message = str(caught.value)
    assert "model kimi-k2.7 not found" in message
    assert "404" in message
    assert "kimi-k2.7" in message
    # The endpoint answered, so suggesting it might be down sends the reader away
    # from the actual cause.
    assert "running" not in message


def test_other_client_errors_still_surface_loudly():
    client = FakeClient(error=OpenAIError("something else broke"))

    with pytest.raises(llm.LLMError, match="something else broke"):
        list(llm.stream_reply(client, "kimi-k2.7", []))
