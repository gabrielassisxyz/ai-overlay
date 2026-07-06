# Milestone C plan — widen: Hyprland summon, capture modes, README

> **For a fresh agent.** This doc is a pickup brief + plan for Milestone C. It assumes
> **no memory of the prior sessions**. Read the orientation docs below first, then follow
> the plan. The durable behavioral contract is [`spec.md`](spec.md) (esp. §3 capture, §5
> interaction, §6-C acceptance); this file sequences the work and flags the risks — it does
> not restate the contract.

## Orientation (read in this order, ~10 min)

1. [`../AGENTS.md`](../AGENTS.md) — how to work here: commands (`uv sync`, `bin/ci`,
   `uv run pytest`), TDD rules, security habits, git conventions. **The "common hurdles"
   list already records the two gotchas C must resolve:** the proxy must be running, and a
   Hyprland-keybind `exec` **inherits no shell env** (so it can't see `AI_OVERLAY_API_KEY`).
2. [`spec.md`](spec.md) — the contract. For C you mostly need **§3 (Capture)** and the
   **§5** launch/interaction rules, plus **§6-C** for acceptance.
3. [`architecture-decisions.md`](architecture-decisions.md) — Decision 3 (hotkey-summoned
   panel) and its **"Refined in Milestone B"** note (attachment model + hot-reload). Don't
   relitigate these.

Milestone B is **PR #3** (`https://github.com/gabrielassisxyz/ai-overlay/pull/3`); its plan
+ revision note is [`milestone-b-plan.md`](milestone-b-plan.md).

## What already exists (build on it, don't rebuild it)

C is mostly **integration + docs**, not new core code. The mechanism is done:

| Piece | State today | Notes for C |
|---|---|---|
| `capture.py` — `fullscreen` / `active-window` / `region` | **All three implemented and unit-tested** (`tests/test_capture.py`, named `FakeRunner`). | The argv-building is covered offline. What's missing is **live validation** and driving the non-fullscreen modes **through the TUI**. |
| TUI attachment model | `/capture` stages a shot; `auto_capture` gates the launch shot; region/slurp already runs on the thread worker so it doesn't freeze the UI. | A profile with `capture = "region"` / `"active-window"` should already work end-to-end — verify it. |
| `/profile` hot-reload, streaming, error surfacing | Done in B. | Untouched by C. |
| Token precedence | `config.resolve_api_key`: `api_key` (raw) > `api_key_env` > env chain > placeholder. **Raw `api_key` already works for a keybind launch.** | C's job is to *decide + document* the delivery, not rebuild resolution. |

Every external seam (`grim`/`slurp`/`hyprctl`, the LLM client) is dependency-injected —
preserve that so tests stay offline.

## Goal & done-check (spec §6-C)

A Hyprland keybind summons the app, it floats/pins above the (windowed/borderless) game,
captures per the active profile, and answers — with a documented setup a new user can
follow. **Done when:** all three capture modes are exercised by tests **and** validated
live; a second real profile exists; the keybind + float window-rule + token delivery are
documented in a README; `bin/ci` green.

## Scope of C (precise)

- **Hyprland summon (the headline):**
  - A keybind (`bind = SUPER, <key>, exec, …`) that launches the app on a chosen profile.
  - A **window rule** that floats + pins the terminal so it sits above the game (record the
    exact `windowrule`/`windowrulev2` in AGENTS.md's hurdles list *and* the README).
  - **Token delivery to the keybind process** (the open AGENTS item — `exec` inherits no
    env). Decide among: raw `api_key` in the local config (already supported), a Hyprland
    `env = AI_OVERLAY_API_KEY,…` line, or a gitignored env file the app loads. **Recommend
    one, document it, never commit a token.** If it needs code (e.g. load a dotenv), keep it
    small and behind the existing `resolve_api_key` precedence.
- **Capture modes — validate + wire, don't rewrite:**
  - Confirm `active-window` and `region` work **through the TUI** (a profile per mode, or
    `/capture` under each). Add a TUI-level test if the wiring isn't already covered.
  - Live-check on the real compositor (can't be a unit test — note results in AGENTS.md).
- **A second real profile** beyond `generic`/`brotato`, proving the mechanism generalizes
  (pick a genuinely different task; add its `profiles/*.md` + a `[profiles.*]` block in
  `config.example.toml`).
- **README** (currently none): what it is, setup (`uv sync`, config, proxy, token), the
  Hyprland keybind + window rule, and the interaction (attachment model, `/capture`,
  `/profile`, `auto_capture`). Use PR #2/#3 as the house style for tone.

## The main technical risk — a global screenshot hotkey vs. a launch-per-summon model

Your stated end goal is *"leave the overlay open, press a hotkey to attach a fresh
screenshot."* That is **harder than it looks** and forces a fork C must decide, not assume:

- **Launch-per-summon (recommended for C):** the keybind starts a fresh instance that
  captures on launch (`auto_capture`); re-looking within that session is the typed
  `/capture`. No IPC, no daemon — fits KISS/YAGNI and closes §6-C. The global "hotkey adds a
  shot to an already-open overlay" stays a later rock.
- **Persistent overlay + global hotkey (the bigger phase):** a long-lived instance that a
  *second* Hyprland keybind signals to `/capture` while the **game** is focused. The app
  can't receive that keypress directly (it's not focused), so this needs **IPC** — a socket
  / named pipe the app listens on, poked by a tiny `exec` command. Real design surface;
  likely its own milestone (call it D), not a bullet in C.

**Flag this to the maintainer and pick before building.** Don't silently build the IPC.

## Decisions already locked (do not relitigate)

- Windowed/borderless games only; no exclusive-fullscreen coverage, no `wlr-layer-shell`
  overlay (that's the deliberate later phase).
- Attachment model + `/profile` hot-reload are settled (B); C does not change interaction.
- Model default `kimi-k2.7`, per-profile override — a config knob.
- Talk only to the proxy on localhost; no direct-vendor call.

## Testing (TDD, offline)

- **Keep the "no real `grim`/`slurp`/`hyprctl`, no network" rule.** Hyprland/compositor
  behavior can't be unit-tested — validate it **live** and record the outcome + exact
  window rule in AGENTS.md; don't fake a green test for it.
- Add tests only where there's real logic: any dotenv/token-loading code, and TUI-level
  coverage that a `region`/`active-window` profile stages + sends (inject the fake capture,
  assert the mode reaches `capture`).
- `bin/ci` green before "done".

## Out of scope for C (YAGNI — flag if a change drifts here)

`wlr-layer-shell`/GTK4 overlay, always-on HUD, exclusive-fullscreen, voice, a persistent
daemon, a general command framework, provider abstraction. The **persistent-overlay global
screenshot hotkey (with IPC)** is likely its own milestone — keep it out of C unless the
maintainer explicitly pulls it in.

## Conventions & workflow (from AGENTS.md — don't rediscover)

- Branch `feature/…` off `master`; small conventional commits; PR to `master` with
  **what + why**. Commit/PR text is **English, no AI/tool attribution** (see PR #2/#3).
- Deps via `uv add`; ruff (line length 88); `bin/ci` must be green; the gitleaks pre-commit
  hook is active after `bin/install-hooks`. Never commit the proxy token.

## Suggested skills

- **`readme-writing`** — for the README (this is the first user-facing doc).
- **`omarchy`** — for the Hyprland keybind, window rule, and screenshot-hotkey wiring
  (`~/.config/hypr/`), since the target is Omarchy.
- **`/run`** / **`verify`** — drive the real summon → capture → answer flow on the
  compositor; live validation is the point of C.
- **`/code-review`** (medium/high) before the PR.
- **Not applicable:** `tui-glamorous` (Go/Charmbracelet — this project is Python + Textual).
