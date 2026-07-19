# Milestone A plan — core loop, no TUI

> **Transient tracking doc** for Milestone A. The durable contract is [`spec.md`](spec.md) §2–§4 and §6-A; this file just sequences the work and is safe to archive once A is done.

## Goal

Prove the whole idea end-to-end **before any UI**: capture the screen → send it to the LiteLLM proxy with a profile prompt → **stream the answer to stdout**. If this works, the risky part (does the model actually read the screen usefully?) is validated for the cost of ~three small modules.

*Done when:* `python -m ai_overlay [--profile X] [question]` streams a real answer; `config`/`capture`/`llm` are unit-tested with fakes (no network, no real `grim`); `bin/ci` is green.

## Deliverables

| File | Responsibility | Key surface |
|---|---|---|
| `ai_overlay/__init__.py` | package marker | — |
| `ai_overlay/config.py` | load + resolve config | `load_config(path) -> Config`; `Config.resolve(name \| None) -> Profile` |
| `ai_overlay/capture.py` | screen → PNG bytes | `capture(mode, *, run, max_width) -> bytes`; `downscale_png(data, max_width)` |
| `ai_overlay/llm.py` | proxy call + stream | `build_messages(system, text, png)`; `stream_reply(client, model, messages) -> Iterator[str]` |
| `ai_overlay/__main__.py` | wire it, stream to stdout | `argparse`: optional `--profile`, optional trailing question |
| `tests/test_config.py` | parse, resolve, errors | — |
| `tests/test_capture.py` | command per mode + downscale (fake `run`) | — |
| `tests/test_llm.py` | message payload + streaming + loud errors (fake client) | — |
| `pyproject.toml` | add runtime deps `openai`, `pillow` | (textual waits for B) |
| `config.example.toml` + `profiles/*.md` | a runnable default profile | — |

## TDD sequence (each step: red → green, then `bin/ci`)

1. **`config.py`** — pure, no I/O deps. Dataclasses `Config` / `Profile`; `load_config` reads TOML (stdlib `tomllib`), fills defaults, expands `~`; `resolve` picks `--profile` else `default_profile`, and on an unknown name raises an error that **lists available profiles**. *Test:* valid parse, default fill, unknown-profile error, missing prompt-file error.
2. **`capture.py`** — `capture(mode)` builds the right command per mode (`fullscreen` → focused monitor via `hyprctl monitors` → `grim -o`; `active-window` → `hyprctl activewindow` geom → `grim -g`; `region` → `slurp` → `grim -g`) via an **injected `run`**; downscale via Pillow. *Test:* each mode issues the expected argv against a **named fake runner**; `downscale_png` shrinks width; real `grim` is never called.
3. **`llm.py`** — `make_client(base_url, api_key)`; `build_messages` puts the profile prompt in `system` and text + base64 `data:` image in `user`; `stream_reply` yields text deltas from an **injected client**; proxy/2xx failures raise a loud, actionable error ("is the proxy on localhost:4000?"). *Test:* payload shape, delta streaming, error message — all against a fake client, **no network**.
4. **`__main__.py`** — parse args, `load_config` → `resolve` → read prompt file → `capture` → `build_messages` → `stream_reply`, printing deltas with flush. Light wiring test; real end-to-end is a manual smoke against the live proxy.

## Decisions pinned for A

- Config format: TOML via stdlib `tomllib` (no dependency).
- API key: env only (`AI_OVERLAY_API_KEY` → `OPENAI_API_KEY` → placeholder if the proxy is keyless). Never in config/git.
- Downscale to `max_image_width` (default 1280) **before** the image leaves the process. Bytes are never logged nor written outside a user-controlled temp.
- Dependency injection (`run`, `client`) is the seam that keeps tests offline — mandated by [`../AGENTS.md`](../AGENTS.md).

## Out of scope for A (lands later)

Textual TUI, `default_profile` UX niceties beyond resolution, `/profile` command, follow-up/history, `active-window`/`region` polish beyond the command builders, Hyprland keybind + float rule. (Full list: [`spec.md`](spec.md) §7.)
