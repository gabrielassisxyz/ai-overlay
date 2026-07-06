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

## Decision 1 — Stack: Python + PyQt6

**Chosen: Python + PyQt6.**

### Options

#### Python + PyQt6 — chosen

Pros:
- Shortest path to a working MVP. Overlay + input + response + screenshot can
  fit in a single ~300-line file.
- The official `anthropic`/OpenAI Python SDKs are clean and support streaming
  (response rendered incrementally). We talk to LiteLLM over the OpenAI-compatible
  client, which is well supported.
- Screenshots are trivial: `subprocess` calling `grim` (ships with Omarchy) →
  bytes → base64. No extra library.
- Frameless, always-on-top, transparent windows work well under Qt on Wayland.
- Customization becomes "edit a `.md` profile file", which matches the goal of
  injecting per-task context.
- Distribution for personal use is simple: a `venv` plus a Hyprland keybind.

Cons:
- The UI is functional, not beautiful. Styling Qt is more work than CSS.
- PyQt on Wayland occasionally needs an env var / window rule tweak.
- Packaging for redistribution is awkward (irrelevant for personal use).

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

The brief is a **simple MVP** that is **easy to customize**. Python delivers both
with the least code and the fewest moving parts — it reaches "it works" fastest,
and can evolve from there. Tauri/Electron are better *destinations* (polished UI,
light binary) but worse *starting points*: doing them first is optimizing before
there's anything to optimize. Path: validate in Python, migrate later if the UI
warrants it.

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

- `overlay.py` — frameless, always-on-top `QWidget`: a message input, a response
  area (streaming), a "capture + send" action.
- Screenshot: `grim` (full screen) or `grim` + `slurp` (region) → base64.
- LLM call: OpenAI-compatible client → `http://localhost:4000/v1`, model and
  system context taken from the active profile.
- Profiles: `profiles/*.md` — injected context + model + screenshot-by-default
  flag.
- Trigger: Hyprland keybind toggles the overlay (via a socket/signal to a running
  instance, or a fresh launch for the first cut).
