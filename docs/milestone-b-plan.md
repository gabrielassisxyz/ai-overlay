# Milestone B plan — the Textual TUI (the actual MVP)

> **For a fresh agent.** This doc is a pickup brief + plan for Milestone B. It assumes
> **no memory of the prior session**. Read the three orientation docs below first, then
> follow the plan. The durable behavioral contract is [`spec.md`](spec.md) (esp. §5, §2,
> §4) and [`spec.md`](spec.md) §6-B for acceptance — this file sequences the work and
> flags the risks; it does not restate the contract.

## Orientation (read in this order, ~10 min)

1. [`../AGENTS.md`](../AGENTS.md) — how to work in this repo: commands (`uv sync`,
   `bin/ci`, `uv run pytest`), TDD rules, security habits, git conventions, and the
   "common hurdles" list. **The hurdles list already records the two gotchas that will
   bite you** (proxy must be running; keybind launch inherits no shell env).
2. [`spec.md`](spec.md) — the contract. For B you mostly need **§5 (Interaction)**,
   plus §2 (config, incl. API-key precedence) and §4 (LLM) which B reuses unchanged.
3. [`architecture-decisions.md`](architecture-decisions.md) — *why* Python + Textual
   (Decision 1) and why route through the LiteLLM proxy (Decision 2). Don't relitigate
   these; they're settled.

Milestone A is merged/under review as **PR #2**
(`https://github.com/gabrielassisxyz/ai-overlay/pull/2`). Its plan is
[`milestone-a-plan.md`](milestone-a-plan.md).

## What already exists (Milestone A — build on it, don't rewrite it)

The core loop works headless today: `python -m ai_overlay [--profile NAME] [question]`
captures the focused monitor, calls the proxy, and streams the answer to **stdout**.
Reuse these as-is — B is a new UI over them:

| Module | What you'll call | Notes |
|---|---|---|
| `ai_overlay/config.py` | `load_config`, `Config.resolve`, `resolve_api_key` | Profiles, defaults, key precedence. **Already handles the key** — B does not touch key logic. |
| `ai_overlay/capture.py` | `capture(mode, *, run, max_width)` | `fullscreen` = focused monitor only. `region` **blocks on the user** (slurp) — must run off the UI thread. |
| `ai_overlay/llm.py` | `make_client`, `build_messages`, `stream_reply` | `stream_reply` is a **blocking** generator of text deltas. Errors raise `LLMError` with an actionable message. |
| `ai_overlay/__main__.py` | current stdout entrypoint | You will rewire this to launch the TUI (see below). |

Every external seam (`grim`/`slurp`/`hyprctl`, the LLM client) is **dependency-injected**
so tests run offline with named fakes. Preserve that seam in the new code — see the
existing `tests/test_capture.py` (`FakeRunner`) and `tests/test_llm.py` (`FakeClient`)
for the pattern to copy.

## Goal & done-check (spec §6-B)

Summon → the app captures per the active profile and streams an answer → type a
follow-up (same conversation) → `/profile` to switch task → quit. **Done when:** that
flow works end-to-end; a Textual `run_test` pilot smoke test passes with injected
fakes; `bin/ci` is green.

## Scope of B (precise)

- **`ai_overlay/app.py` — a Textual `App`:**
  - **Injectable deps** (constructor params: the config, a `capture` callable, and an
    LLM client) so `run_test` stays offline. This is the single most important design
    choice for testability — mirror how A injects `run`/`client`.
  - **First turn:** on mount, capture per the active profile's mode, send with the
    initial question (if any) else profile-only, stream the answer into a response pane.
  - **Follow-up:** plain text in the input box continues the **same conversation**
    (append to the in-memory `messages` list). A follow-up does **NOT** re-capture the
    screen (a future `/recapture` is explicitly out of scope — spec §5).
  - **Commands** — parse only a leading `/`; the **only** command is `/profile`. This is
    NOT a general command framework (don't add `/help`, `/model`, …):
    - `/profile` → list available profiles, marking the active one.
    - `/profile <name>` → switch the active profile for **subsequent** asks; does not
      rewrite history and does not re-capture.
  - **Quit:** `Esc` / `Ctrl+C`.
- **Rewire `__main__.py`:** the TUI becomes the default action. **Recommendation:** keep
  the A stdout path behind a `--print` (headless one-shot) flag — it's useful for
  scripting and quick debugging without a TTY. `default_profile` resolution already
  works (A), so a bare `python -m ai_overlay` launches on the default profile.
- **Add the dep:** `uv add textual` (declare it as A did for pillow/openai).

## The main technical risk — streaming without freezing the UI

`stream_reply` and `capture` are **blocking**. Do not call them on Textual's event loop
or the UI will freeze. Use a **Textual worker** (`@work(thread=True)` / `run_worker`) to
run the blocking call in a thread and post each delta back to the widget (via
`call_from_thread` or by updating a reactive). Budget your first spike on proving this
path with a fake client that yields a few deltas with sleeps. Secondary decision:
**how to render streamed Markdown** — simplest is to accumulate text and update a
`Markdown` widget as it grows; if that's too heavy, stream into a `RichLog`/`Static` and
render Markdown once the turn completes. Pick one, note the choice in the code (no silent
decisions).

## Decisions already locked (do not relitigate)

- Streaming on; **fresh session per invocation** (history lives only for the popup).
- Vision/model default `kimi-k2.7`, per-profile override — a config knob, not code.
- Key handling is done in `config.resolve_api_key`; B reuses it untouched.

> **Revised during implementation (authoritative: spec §5).** Two bullets above were
> changed after a maintainer review, so B ships the interaction the tool is actually
> for — not the first sketch:
> - **Capture is an attachment model, not auto-only.** `/capture` stages a screenshot
>   sent with the next message; a plain message (no new shot) is the follow-up; a new
>   `/capture` is the re-look. `auto_capture` (config, default `true`) gates the launch
>   shot. So there are **two** commands now (`/profile`, `/capture`) — still not a
>   framework. The screenshot *hotkey* remains a Milestone C item.
> - **`/profile` hot-reloads.** Each send rebuilds `[system(active profile)] + history
>   + turn`, so a switch applies the new prompt/model from the next message (history is
>   kept, not rewritten). Rationale + mitigations: architecture-decisions.md, Decision 3.

## Testing (TDD, offline)

- Drive the app with Textual's `App.run_test()` pilot. Inject a fake `capture` (returns
  fixed PNG bytes) and a `FakeClient` (copy from `tests/test_llm.py`) that yields deltas.
- Cover: first answer renders; a typed follow-up appends to `messages` and streams; the
  `/profile` list shows profiles; `/profile <name>` switches the active profile;
  `LLMError` surfaces as a visible message (no crash); quit works.
- Keep the A rule: **no real network, no real `grim`** in any test.

## Out of scope for B (stays for C — spec §7)

`active-window`/`region` end-to-end polish beyond what A built, the Hyprland keybind +
float/pin window rule (and documenting them in the README), and how a keybind-launched
process receives the proxy token (the open item flagged in AGENTS.md). No
`wlr-layer-shell` overlay, no persistent HUD.

## Conventions & workflow (from AGENTS.md — don't rediscover)

- Branch `feature/mvp-tui` off `master`; small conventional commits; PR to `master` with
  **what + why**. Commit/PR text is **English, no AI/tool attribution** (see PR #2 as the
  house style).
- Deps via `uv add`; format+lint with ruff (line length 88); `bin/ci` must be green
  before "done"; the gitleaks pre-commit hook is active after `bin/install-hooks`.
- To try it live you need `~/.config/ai-overlay/config.toml` (copy `config.example.toml`),
  the profile prompt files, the LiteLLM proxy on `localhost:4000`, and the proxy token in
  the env (`AI_OVERLAY_API_KEY`) or config. Never commit the token.

## Suggested skills

- **`/run`** and **`verify`** — drive the actual TUI to confirm the summon→ask→follow-up
  flow works, not just the unit tests.
- **`/code-review`** (medium/high) before opening the PR.
- **`research-software`** — if you need current Textual patterns for **threaded workers +
  streaming updates** and the `run_test` pilot API; verify against installed version, not
  memory.
- **`claude-api`** — reference for OpenAI-compatible **streaming** semantics if you touch
  the LLM path (we call it through the proxy; you shouldn't need to, but useful if deltas
  misbehave).
- **Not applicable:** `tui-glamorous` (that's Go / Charmbracelet — this project is
  Python + Textual). Ignore any hook that suggests it.
