"""Tests for screen capture command-building and downscaling (docs/spec.md §3).

A named fake stands in for the subprocess runner: real grim/slurp/hyprctl are never
called, and we assert the exact argv each mode issues.
"""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from ai_overlay import capture as cap


def _png(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(out, format="PNG")
    return out.getvalue()


class FakeRunner:
    """Records argv and answers per command; the anti-`grim` in tests."""

    def __init__(self, *, geometry: str = "0,0 100x100", window=None, monitors=None):
        self.calls: list[list[str]] = []
        self._geometry = geometry
        self._window = window or {"at": [10, 20], "size": [640, 480]}
        self._monitors = monitors or [
            {"name": "DP-1", "focused": True},
            {"name": "HDMI-A-1", "focused": False},
        ]

    def __call__(self, argv: list[str]) -> bytes:
        self.calls.append(argv)
        tool = argv[0]
        if tool == "grim":
            return _png(200, 100)
        if tool == "slurp":
            return f"{self._geometry}\n".encode()
        if tool == "hyprctl":
            payload = self._monitors if argv[1] == "monitors" else self._window
            return json.dumps(payload).encode()
        raise AssertionError(f"unexpected command {argv!r}")


def _is_png(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def test_fullscreen_captures_only_the_focused_output():
    run = FakeRunner()
    result = cap.capture("fullscreen", run=run, max_width=1280)
    assert run.calls == [
        ["hyprctl", "monitors", "-j"],
        ["grim", "-o", "DP-1", "-"],  # only the focused monitor, not the whole layout
    ]
    assert _is_png(result)


def test_fullscreen_without_a_focused_monitor_raises():
    run = FakeRunner(monitors=[{"name": "DP-1", "focused": False}])
    with pytest.raises(cap.CaptureError, match="No focused monitor"):
        cap.capture("fullscreen", run=run)


def test_active_window_builds_geometry_from_hyprctl():
    run = FakeRunner(window={"at": [10, 20], "size": [640, 480]})
    cap.capture("active-window", run=run)
    assert run.calls == [
        ["hyprctl", "activewindow", "-j"],
        ["grim", "-g", "10,20 640x480", "-"],
    ]


def test_region_uses_slurp_geometry():
    run = FakeRunner(geometry="5,5 800x600")
    cap.capture("region", run=run)
    assert run.calls == [
        ["slurp"],
        ["grim", "-g", "5,5 800x600", "-"],
    ]


def test_region_cancelled_raises():
    run = FakeRunner(geometry="")
    with pytest.raises(cap.CaptureError, match="cancelled"):
        cap.capture("region", run=run)


def test_unknown_mode_raises():
    with pytest.raises(cap.CaptureError, match="Unknown capture mode"):
        cap.capture("webcam", run=FakeRunner())


def test_downscale_shrinks_wide_image():
    shrunk = cap.downscale_png(_png(2000, 1000), max_width=1280)
    with Image.open(io.BytesIO(shrunk)) as image:
        assert image.size == (1280, 640)


def test_downscale_leaves_small_image_untouched():
    original = _png(400, 300)
    result = cap.downscale_png(original, max_width=1280)
    with Image.open(io.BytesIO(result)) as image:
        assert image.size == (400, 300)


def test_capture_downscales_with_given_max_width():
    run = FakeRunner()  # grim returns a 200x100 png
    result = cap.capture("fullscreen", run=run, max_width=50)
    with Image.open(io.BytesIO(result)) as image:
        assert image.width == 50


# The two failures below use throwaway commands rather than the capture tools: the
# point is what the wrapper says about a failure, which needs a real subprocess to
# fail and no display to do it.


def test_missing_command_says_how_to_get_it():
    with pytest.raises(cap.CaptureError) as caught:
        cap._default_run(["ai-overlay-no-such-command"])

    message = str(caught.value)
    assert "grim" in message and "slurp" in message
    # Naming one distribution as where the tools come from tells every other reader
    # nothing; the message has to point at a package, not at a setup.
    assert "Omarchy" not in message


def test_failed_command_keeps_the_tool_output_and_explains_it():
    with pytest.raises(cap.CaptureError) as caught:
        cap._default_run(["sh", "-c", "echo 'failed to create display' >&2; exit 1"])

    message = str(caught.value)
    assert "failed to create display" in message  # the tool's own words survive
    assert "Wayland" in message  # and are no longer the whole message
