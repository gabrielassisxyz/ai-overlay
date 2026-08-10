# Roadmap

What exists, what is missing, and what is deliberately out of scope. Details: [README](README.md), [docs/spec.md](docs/spec.md), [docs/architecture-decisions.md](docs/architecture-decisions.md).

## What exists today

- **Core loop** — screenshot capture → local LiteLLM proxy (OpenAI-compatible, `localhost:4000`) → streamed multimodal answer.
- **Textual TUI (the MVP surface)** — streaming answer pane, input box, the attachment model (`/capture` stages a shot sent with the next message; `auto_capture` gates the launch shot), in-session follow-up, `/profile` hot-reload, `F2` re-capture.
- **Three capture modes** — `fullscreen`, `active-window`, `region` (`slurp`), selectable per profile and unit-tested.
- **Profiles** — task behavior lives in `profiles/*.md` plus a TOML block in the user config; a new use case is a new text file, no code change. Two real profiles exist (`brotato`, `generic`).
- **Hyprland integration** — keybind launch in a dedicated floating terminal, float/pin/center window rules, and a documented path for getting the proxy token to keybind-launched processes (README "Hyprland setup").
- **Harness:** `bin/ci` (ruff format + lint, pytest, pip-audit, proxy reachability probe, markdown soft-wrap check, prose gate), gitleaks pre-commit hook, matching GitHub Actions workflows.

## Missing / natural next steps

- **`wlr-layer-shell` overlay** — a GTK4 + gtk4-layer-shell transparent panel that draws above even fullscreen apps. The intended "make it right" surface; deliberately deferred until the TUI proves the idea.
- **Vision escalation** — add stronger vision models to the proxy if dense-UI reading with the default model proves weak.
- **More profiles** — grow the profile library as real tasks appear; the mechanism needs no code change.

## Deliberately out of scope

- Always-on HUD and any persistent daemon / global re-capture hotkey — the app is a fresh popup per invocation.
- Exclusive-fullscreen coverage — borderless windowed is the supported workaround.
- Voice input, and a text-only mode without capture.
- A general slash-command framework.
- A provider abstraction — the LiteLLM proxy already provides one; the model is just a parameter.
