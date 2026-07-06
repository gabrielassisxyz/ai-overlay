# ai-overlay — Agent Briefing

> Read before every interaction. Living spec: short, imperative. On every gotcha or
> decision, append one line here. General engineering + git conventions live in the
> maintainer's global agent config — this file holds only what's specific to this repo.

> **What it is:** a hotkey-summoned AI assistant panel for Linux (Hyprland / Wayland) —
> screenshot the foreground app, send it to an LLM via a local LiteLLM proxy with a
> per-task profile injected, read the answer. Task behavior is driven by `profiles/*.md`.

## Stack & Commands
- **Stack:** Python (uv-managed, `.python-version` = 3.13) + PyQt6 overlay + OpenAI-compatible
  `openai` client → local LiteLLM proxy (`http://localhost:4000/v1`). See
  [docs/architecture-decisions.md](docs/architecture-decisions.md) for the why.
- **Setup:** `uv sync` (creates `.venv` with dev tools) then `bin/install-hooks` (once).
- **Run:** `uv run python overlay.py` *(entrypoint lands with the MVP)*.
- **Test:** `uv run pytest` (none yet — planning stage).
- **All CI checks:** `bin/ci` (ruff format + lint, pytest, pip-audit).
- **Sandbox (optional):** `ai-jail claude` runs the agent OS-fenced (project read-write,
  host read-only, `~/.ssh`/`~/.gnupg`/`~/litellm` unreachable, `.env` masked) — pair it with
  dangerous permissions, e.g. `ai-jail claude --dangerously-skip-permissions`. Config: `.ai-jail`.

## Scope (current)
- **Current scope:** planning-stage MVP — a personal, local-only overlay for reading game
  screenshots (Brotato etc.) and getting item advice; behavior via swappable text profiles.
  Don't expand beyond it without a present need (no always-on HUD, no exclusive-fullscreen
  support, no provider abstraction — the proxy already gives that). If a change drifts past
  it, STOP and flag it.

## Tests (TDD)
- Every feature is born with a test; every bugfix with a regression test.
- Tests run with ONE command (`uv run pytest`), no manual setup, no real network/proxy —
  mock the LLM call and `grim` with a named fake. If it can't run headless, it's wrong.
- Before saying "done", run `bin/ci` and show the result.

## Small releases
- Every commit on `master` passes `bin/ci` and is runnable — no "broken commit I fix in the
  next one". Branch off `master`, PR back (conventions are in the global config).
- If I forget to commit closed work before switching tasks, remind me.

## Security (habit, not a phase)
- Screenshots can capture anything on screen — never log image bytes or write them to disk
  outside a temp path the user controls; downscale before sending (cost + exposure).
- The LiteLLM proxy holds the keys; this app must not embed any API key. Talk only to
  `localhost:4000`. Flag any change that adds a direct-vendor call or a new outbound host.
- Dependency CVEs are caught by `pip-audit` in `bin/ci` / CI.

## Git & secrets
- Before any commit, show `git status` + `git diff --cached`; confirm no secret is staged.
  The gitleaks pre-commit hook is the deterministic backstop; this habit is the probabilistic
  one. Run `bin/install-hooks` once per clone so the hook is active.
- Real secrets stay out of git — only `*.env.example` with fake values is committed.

## Post-implementation checklist (run before "done")
1. New tests written and passing.
2. `bin/ci` green.
3. `git diff --cached` reviewed — zero secrets.
4. Commits small and well-described.
5. Refactoring candidates listed (if the change was large).
6. Security risks flagged (if you touched screenshots, the network, or the filesystem).
7. Docs / this spec updated if behavior, setup, or commands changed.

## Common hurdles (append as discovered)
- `bin/ci` tolerates `pytest` exit code 5 (no tests collected) while none exist; it fails on
  any real test failure and enforces strictly the moment the first test lands.
- Runtime deps (PyQt6, openai) are declared in `pyproject.toml` only once code imports them —
  `dependencies` is intentionally empty during planning.
- PyQt6 on Wayland may need an env var / Hyprland window rule; note the exact fix here when hit.
- The LiteLLM proxy must be running for the app to work; a failed call should say so loudly.
