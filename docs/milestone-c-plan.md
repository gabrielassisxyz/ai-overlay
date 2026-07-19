# Milestone C plan — widen: Hyprland integration + screenshot hotkey

> **For a fresh agent.** Pickup brief + plan for Milestone C. Assumes **no memory of the prior sessions**. Read the orientation docs below first, then follow the plan. The durable behavioral contract is [`spec.md`](spec.md) (§3 capture, §5 interaction, §6-C acceptance, §7 out-of-scope) — this file sequences the work; it does not restate the contract.

## Orientation (read in this order)

1. [`../AGENTS.md`](../AGENTS.md) — how to work here: `uv sync`, `bin/ci`, `uv run pytest`, TDD, git conventions, and the **common hurdles** list (the keybind-env hurdle is the one C finally closes).
2. [`spec.md`](spec.md) — the contract. For C: **§3** (the three capture modes), **§5** (the screenshot hotkey note), **§6-C** (acceptance), **§7** (what stays out).
3. [`architecture-decisions.md`](architecture-decisions.md) — Decisions 1–3 are settled; Decision 4 (how a keybind-launched process gets the proxy token) is **added in this milestone**.

Milestones A and B are merged on `feature/mvp-tui` (see the git log). The B brief is [`milestone-b-plan.md`](milestone-b-plan.md).

## What already exists (don't rebuild it)

- **All three capture modes** are implemented in `ai_overlay/capture.py` (`fullscreen` / `active-window` / `region`) and **unit-tested** in `tests/test_capture.py`. The TUI already passes the active profile's mode to the injected `capture` callable (`app.py` → `_worker_turn` / `_worker_capture`).
- **Two real profiles** exist: `profiles/brotato.md` and `profiles/generic.md`.
- `config.py` validates `capture` against `CAPTURE_MODES`, so a profile can already select any of the three modes with zero code change.

So the formal §6-C "done when" (three modes exercised by tests) is met at the *unit* layer. C is about the pieces B explicitly deferred: the **Hyprland glue**, the **keybind token decision**, and the **in-app screenshot hotkey** — plus exercising the modes through the TUI and correcting stale docs.

## Scope of C (precise)

1. **Screenshot hotkey (`app.py`).** A Textual key binding (`F2`) that stages a screenshot exactly like `/capture`, so the user re-looks without typing the command (spec §5 note, §7 lists this as the C item). Guard it so it can't fire while a turn/capture is already in flight. Mention it in the idle help line and the input placeholder. It is **not** a global/daemon hotkey (that's out of scope §7 — the app is a fresh popup per invocation); it's an in-app binding.
2. **Exercise all three modes through the TUI (`tests/test_app.py`).** `fullscreen` is already covered by the launch test. Add: (a) the hotkey stages a shot; (b) the app passes `active-window` and `region` straight through to the capture callable. Keep the offline rule — a fake `capture` records the mode; no real `grim`/`slurp`.
3. **Hyprland setup docs (`README.md`).** A "Hyprland setup" section: the `bind =` keybind (default profile + a `--profile` variant), the float/pin/center `windowrule`s targeting the overlay terminal by class, and how the launched process receives the proxy token. Also fix the stale bits: the "planning — no code yet" status block and the `Stack: Python + PyQt6` row (it's Python + Textual — Decision 1).
4. **Token-to-keybind decision (`architecture-decisions.md`, `AGENTS.md`).** A Hyprland `exec` keybind inherits **no** interactive-shell env, so `$AI_OVERLAY_API_KEY` is empty under a keybind launch. Record the resolution as **Decision 4** and close the open item there and the matching `AGENTS.md` hurdle. **No code** — `config.resolve_api_key` already supports the env chain and a raw `api_key`; C only decides + documents which path to use.
5. **`config.example.toml`.** Show the `capture = "active-window" | "region"` option and a one-line pointer to the keybind-token note.

Decision 4 (recommended path, plaintext trade-off flagged for a single-user machine):
- **Preferred:** put the token in the compositor env via a **gitignored** Hyprland include (`env = AI_OVERLAY_API_KEY,<token>` in a `source`d secrets file). Keeps the token out of both this repo and the app's own config file; inherited by every `exec` child.
- **Fallback:** a raw `api_key` in `~/.config/ai-overlay/config.toml` (already supported) — self-contained, simplest, plaintext in the app config.

## Out of scope for C (stays out — spec §7)

`wlr-layer-shell` overlay, always-on HUD, a persistent daemon / global re-capture hotkey, exclusive-fullscreen coverage, voice input, a general slash-command framework, a provider abstraction. Do **not** invent extra profiles — two real ones already exist; the modes get exercised via tests + docs, not by adding profiles nobody asked for.

## Done-check (spec §6-C)

- `F2` stages a screenshot in the running TUI (no `/capture` typed); a pilot test proves it.
- Pilot tests exercise `active-window` and `region` through the app (fullscreen already is).
- README documents the keybind + float/pin window-rule + the token path; stale status/stack bits corrected.
- Decision 4 recorded; the `AGENTS.md` keybind-env hurdle closed.
- `bin/ci` green.

## Conventions (from AGENTS.md — don't rediscover)

Work on `feature/mvp-tui`; small conventional commits; PR to `master` with **what + why**. All file content **English, no AI/tool attribution**. Deps via `uv add`; ruff (line length 88); `bin/ci` green before "done"; gitleaks pre-commit hook active after `bin/install-hooks`.

## Suggested skills

- **`/run`** / **`verify`** — drive the real TUI to confirm `F2` re-looks end-to-end.
- **`/code-review`** (medium/high) before the PR.
