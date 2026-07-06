"""Capture the screen as PNG bytes (docs/spec.md §3).

Every external command goes through an injected ``run`` callable so tests use a
named fake and never touch real ``grim`` / ``slurp`` / ``hyprctl``. The image is
downscaled before it is returned, so nothing full-resolution ever leaves here.
"""

from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Callable

from PIL import Image

from ai_overlay.config import DEFAULT_MAX_IMAGE_WIDTH

# Runs an argv and returns its stdout bytes (PNG for grim, text for hyprctl/slurp).
RunCommand = Callable[[list[str]], bytes]


class CaptureError(Exception):
    """A capture command was missing, cancelled, or failed."""


def _default_run(argv: list[str]) -> bytes:
    try:
        result = subprocess.run(argv, capture_output=True, check=True)
    except FileNotFoundError as err:
        raise CaptureError(
            f"Command not found: {argv[0]!r}. Is it installed? "
            "(Omarchy ships grim/slurp.)"
        ) from err
    except subprocess.CalledProcessError as err:
        detail = err.stderr.decode(errors="replace").strip() or f"exit {err.returncode}"
        raise CaptureError(f"{argv[0]!r} failed: {detail}.") from err
    return result.stdout


def capture(
    mode: str,
    *,
    run: RunCommand = _default_run,
    max_width: int = DEFAULT_MAX_IMAGE_WIDTH,
) -> bytes:
    """Grab the screen for ``mode`` and return downscaled PNG bytes."""
    if mode == "fullscreen":
        png = run(["grim", "-o", _focused_output(run), "-"])
    elif mode == "active-window":
        png = run(["grim", "-g", _active_window_geometry(run), "-"])
    elif mode == "region":
        png = run(["grim", "-g", _selected_region(run), "-"])
    else:
        raise CaptureError(f"Unknown capture mode {mode!r}.")
    return downscale_png(png, max_width)


def _focused_output(run: RunCommand) -> str:
    """Return the name of the monitor with focus, so fullscreen grabs only it."""
    monitors = json.loads(run(["hyprctl", "monitors", "-j"]))
    for monitor in monitors:
        if monitor.get("focused"):
            return monitor["name"]
    raise CaptureError("No focused monitor reported by hyprctl.")


def _active_window_geometry(run: RunCommand) -> str:
    """Ask Hyprland for the focused window's box as a grim ``-g`` geometry string."""
    data = json.loads(run(["hyprctl", "activewindow", "-j"]))
    x, y = data["at"]
    width, height = data["size"]
    return f"{x},{y} {width}x{height}"


def _selected_region(run: RunCommand) -> str:
    """Let the user drag a region with slurp; returns a grim ``-g`` geometry string."""
    geometry = run(["slurp"]).decode().strip()
    if not geometry:
        raise CaptureError("Region selection was cancelled.")
    return geometry


def downscale_png(data: bytes, max_width: int) -> bytes:
    """Shrink the image to ``max_width`` (keeping aspect) and re-encode as PNG."""
    with Image.open(io.BytesIO(data)) as image:
        if image.width > max_width:
            height = round(image.height * max_width / image.width)
            image = image.resize((max_width, height))
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()
