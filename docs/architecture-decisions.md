# Architecture decisions — ai-overlay MVP

This document records the three decisions that shape the MVP: the application
**stack**, the **LLM connection**, and the **overlay behavior**. For each, the
chosen option is stated first, followed by the alternatives with their trade-offs
and the reason the choice was made.

Context that drives all three: the target environment is **Omarchy = Hyprland +
Wayland**, and the initial use case (games like Brotato, Bounty of One, Vampire
Survivors) runs **windowed / borderless**, not exclusive fullscreen. That
single fact removes most of the hard problems.

---

## Decision 1 — Stack: Python + Textual (TUI)

**Chosen: Python + Textual**, a floating-terminal TUI summoned by a Hyprland
keybind. A `wlr-layer-shell` GTK4 overlay is the intended "make it right" surface
later — deliberately **not** the MVP.

### Revised from an earlier PyQt6 pick

An earlier pass chose Python + **PyQt6** (a frameless always-on-top QWidget). The
requirements interview kept Python but moved the MVP surface to a **TUI**: the
target is Omarchy (keyboard-driven Hyprland), streaming Markdown + a text input +
in-session follow-up are what Textual does out of the box, and a floating terminal
pinned by a Hyprland window rule already "sits on top" of the windowed/borderless
games in scope. The polished transparent overlay (drawing above even fullscreen)
is a real later phase, and its Wayland-native form is `wlr-layer-shell` + GTK4
(gtk4-layer-shell), not PyQt6 — Qt's layer-shell story on Wayland is weak.

### Options

#### Python + Textual (TUI) — chosen

Pros:
- Shortest path to the actual MVP feature set: a streaming response area, a
  message input, and multi-turn follow-up are built-in Textual widgets; Markdown
  (what LLM answers are) renders natively.
- Keyboard-driven and terminal-native — matches Omarchy's ergonomics.
- Same trivial screenshot path (`subprocess` → `grim`/`slurp`) and the same
  OpenAI-compatible `openai` streaming client.
- Runs headless in tests via Textual's `run_test` pilot harness.
- Customization stays "edit a `.md` profile file".

Cons:
- It's a terminal window floated by a Hyprland rule, not a bespoke transparent
  overlay — fine for the windowed/borderless games in scope, but the sleek
  always-on-top look waits for the layer-shell phase.
- No exclusive-fullscreen coverage (out of scope anyway; borderless is the out).

#### Python + PyQt6 (GUI overlay) — superseded

The prior pick — a frameless transparent QWidget is a nicer "overlay" shape, but
styling Qt is more work than the TUI, Qt's Wayland/layer-shell support is weak, and
it doesn't match the keyboard-first flow. Kept only as a reference for what the
eventual overlay should feel like; the real overlay phase will be GTK4 +
gtk4-layer-shell, not Qt.

#### Electron / web

Pros: gorgeous, easy UI (HTML/CSS/React); transparency and animation are
natural; large ecosystem; it is essentially how "natively" works, so the model
is familiar.

Cons: heavy — a full Chromium + Node process competing with the game for RAM/CPU;
more boilerplate (main + renderer + IPC just to take a screenshot); it walks
back toward the same weight that motivated building something new.

#### Tauri (Rust + web)

Pros: web UI (as pretty as Electron) but a light binary (~10 MB, uses the system
webview); fast, lean result; good native window / global-hotkey support.

Cons: largest initial setup and a Rust learning curve on the backend, which
contradicts "simple MVP"; `grim` integration is more ceremony than a Python
`subprocess`; overkill for a personal prototype — the payoff (light binary) only
matters at distribution time.

### Rationale

The brief is a **simple, easy-to-customize MVP** whose UX centerpiece is streaming
an LLM's Markdown answer with follow-up. Python + Textual reaches "it works"
fastest for exactly that shape, stays keyboard-native for Omarchy, and tests
headless. Electron/Tauri remain better *destinations* than *starting points*
(optimizing before there's anything to optimize); the prettier transparent overlay
is a deliberate later phase (GTK4 + `wlr-layer-shell`), not a reason to slow the
MVP.

---

## Decision 2 — LLM connection: local LiteLLM proxy

**Chosen: the existing local LiteLLM proxy** (`http://localhost:4000/v1`,
OpenAI-compatible), with **`kimi-k2.7` as the default vision model** and Gemini
as the escalation path. The app never talks to a model vendor directly — it
talks to the proxy, and the model is just a parameter set per profile.

### Correction embedded here

An earlier pass claimed the proxy only exposed text-only models and that the
screenshot flow would need a new vision model added. **That was wrong.** Of the
models already configured in the proxy (`glm-5.1`, `kimi-k2.7`, `deepseek-v4-*`),
`kimi-k2.7` maps to `openai/kimi-k2.7-code:cloud` on Ollama Cloud, which is
**natively multimodal via the MoonViT vision encoder** (image + video input,
256K context). So a vision-capable model is available today with **no config
change**. The error came from consulting only Moonshot's `platform.kimi.ai` docs
(which frame it as a coding model) and missing the Ollama Cloud model page.

Honest caveat that still holds: "accepts image input" is not the same as "reads
dense game UI well" (small icons, numbers, tooltips, item stacks). MoonViT's
multimodal support is a fact; its OCR/UI-reading *quality* is unverified. So the
plan is: start with `kimi-k2.7` (cheap, zero setup, validates the end-to-end
flow); if item/stat reading is unreliable, escalate by adding a strong vision
model to the proxy — `gemini-3.5-flash` (cheap + strong) or `gemini-3.1-pro` —
which is a new `model_name` in the LiteLLM config, no app change.

### Options

#### Local LiteLLM proxy — chosen

Pros:
- Reuses existing routing, API keys, and failover already configured in
  `~/litellm` — nothing new to wire up.
- OpenAI-compatible endpoint: the app uses one standard client and stays
  vendor-agnostic by construction.
- The model is a per-profile parameter; swapping `kimi-k2.7` → `gemini-3.5-flash`
  needs no code change.
- Keys live in the proxy, not scattered in the app.

Cons:
- Adds a hop (the proxy must be running).
- The specific served model's vision quality depends on the backend
  (Ollama Cloud), which we don't control.

#### Direct Claude API (vision)

Pros: strong vision, ideal for reading item-dense screenshots; clean SDK,
streaming. Cons: bypasses the proxy and its existing keys/routing; another key to
manage in the app; per-use cost. Rejected because the proxy already fronts a
multimodal model and keeps the app provider-agnostic.

#### Direct OpenAI (GPT vision)

Pros: competent vision; lots of tooling. Cons: no specific advantage over routing
through the proxy for this use case; still a direct-vendor coupling.

#### Local Ollama (llava / local vision)

Pros: free per use, fully private, no key, runs on the GPU. Cons: local vision is
markedly weaker at dense game UI — the worst case for this use; competes with the
game for VRAM. Reasonable only as a text-only fallback or if privacy is
non-negotiable.

#### Provider abstraction from day one

Pros: swap providers by config, flexible long term. Cons: extra code and a
premature abstraction for an MVP (violates KISS/YAGNI). Rejected — but note the
proxy *already provides* this abstraction for free, so we get the benefit without
building it.

### Rationale

Vision quality is the critical requirement for a "look at the screen and pick the
item" assistant, and the proxy already fronts a multimodal model
(`kimi-k2.7`/MoonViT). Routing through LiteLLM reuses existing infrastructure,
keeps the app vendor-agnostic behind one OpenAI-compatible client, and makes
model choice a per-profile knob with a clean escalation to Gemini if needed.

---

## Decision 3 — Overlay behavior: hotkey-summoned panel

**Chosen: a panel summoned by a global hotkey.**

### Options

#### Hotkey-summoned panel — chosen

Pros:
- Matches how these games run (windowed / borderless), so a Wayland overlay sits
  on top without workarounds.
- Natural flow: `SUPER+A` → appears → ask → read → `ESC` hides. Doesn't clutter
  the screen while playing.
- The global keybind is trivial in Hyprland (`bind = SUPER, A, exec, ...`), so the
  app needs no global keyboard capture.
- Smallest bug surface.

Cons: not "always present" — it must be summoned. But for item decisions (shop /
level-up moments) that is exactly the right timing.

#### Always-visible HUD

Pros: immersive, info always at hand, no summoning. Cons: covers part of the
game screen (these games have dense corner HUDs); needs focus / click-through
handling so it doesn't steal clicks — more complexity; easy to become a
distraction. Better as an optional v2 mode ("pin to corner").

#### Cover exclusive fullscreen

Pros: necessary *if* a game runs true exclusive fullscreen. Cons: on Wayland,
overlaying exclusive fullscreen is the hard path (layer-shell, or forcing the
game to borderless via a window rule) and inflates MVP scope for a problem we
probably don't have. If a specific game needs it, the easy out is running that
game in **borderless windowed** (available in most of them), and the summoned
panel already covers it.

### Rationale

Maximum usefulness with minimum Wayland friction. The summoned panel is the
format that "just works", so it is the MVP choice; the HUD mode is deferred.

### Refined in Milestone B — attachment model + profile hot-reload

Building B surfaced two behavioral choices the earlier prose left implicit; the
maintainer settled them, so they are recorded here (the contract lives in spec §5).

- **Capture is an attachment, not an implicit act.** A screenshot is *staged* and
  sent with the next message. `auto_capture=true` stages+sends on launch (keeps the
  summon-and-ask flow); `auto_capture=false` opens idle and `/capture` stages on
  demand. This matches the intended use — leave the panel open, capture at a decision
  point, type, send together — and folds "follow-up" (send with no new shot) and
  "re-look" (`/capture` again) into one model instead of a special `/recapture`. The
  screenshot *hotkey* (staging without typing `/capture`) is the only piece left for C.
- **`/profile` hot-reloads.** Rejected alternative: freeze the system prompt at the
  first turn (switching only changes the model) — technically simplest but nearly
  useless mid-session and confusing. Chosen: rebuild `[system(active profile)] +
  history + turn` on every send, so a switch applies the new prompt/model from the
  next message while keeping the conversation and the staged image. The known cost —
  earlier turns were written under the old persona — is mitigated cheaply: accept it
  (the current system prompt dominates), prepend a one-line transition note so the
  model sees an explicit pivot, and write profiles defensively about a possibly stale
  image. A "hard switch" that drops history was rejected (contradicts keeping context).

---

## Open items / risks

- **Vision quality on dense UI is unproven** for `kimi-k2.7`/MoonViT. First real
  test of the MVP is whether it reliably reads items/stats from a screenshot; if
  not, escalate to Gemini via the proxy.
- **Cost** scales with image tokens. Downscale the screenshot before sending
  (region capture via `slurp`, or resize) to keep cost down.
- **Exclusive-fullscreen games** are out of scope for the MVP; workaround is
  borderless windowed.
- **Proxy dependency**: the LiteLLM proxy must be running for the app to work.

## Proposed MVP shape (for the follow-up implementation plan)

- `ai_overlay/` package, run as `python -m ai_overlay --profile <name>` from a
  Hyprland keybind. Flat, small modules:
  - `config.py` — load `~/.config/ai-overlay/config.toml`; resolve a profile to
    (capture mode, system-prompt file, model). Typed dataclasses; a clear error on
    an unknown profile.
  - `capture.py` — `capture(mode) -> PNG bytes` via `grim` (fullscreen / output),
    `grim` + `slurp` (region), or `hyprctl activewindow` geometry (active window);
    downscale before returning (cost + exposure). Subprocess runner injected so
    tests use a named fake — never real `grim`.
  - `llm.py` — OpenAI-compatible `openai` client pinned to
    `http://localhost:4000/v1`; `stream_reply(messages) -> Iterator[str]`;
    multimodal message built with the image as a base64 data URL; talks only to
    localhost; a failed call fails loudly. Client injected for tests.
  - `app.py` — Textual TUI: shows the profile, streams the answer, a text input for
    follow-up, conversation history in memory for the session.
  - `__main__.py` — arg parse (`--profile`, optional initial text) and wiring.
- Profiles: TOML blocks in `config.toml` → `profiles/*.md` prompt files; each sets
  its capture mode. Default model `kimi-k2.7` (Decision 2).
- Trigger: Hyprland keybind runs a fresh instance (no daemon for the first cut); a
  Hyprland window rule floats + pins the terminal.

Milestones:
- **A — core loop, no TUI:** `config` + `capture` + `llm` wired into a one-shot
  that streams the answer to stdout. Proves capture → LiteLLM → answer end-to-end
  before any UI. The "validate the idea before infra" checkpoint.
- **B — the MVP:** Textual TUI on top of A, adding the input box + in-session
  follow-up.
- **C — widen:** active-window + region capture modes; a second profile; the
  Hyprland keybind + float rule documented.
