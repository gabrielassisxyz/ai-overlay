# ai-overlay

A generic, customizable AI assistant overlay for Linux (Hyprland / Wayland).

Summon a panel over whatever you're doing, optionally grab a screenshot, send it
to an LLM with task-specific context injected, and read the answer — without
alt-tabbing out of the foreground app.

The first target use case is **games** (Brotato, Bounty of One, Vampire Survivors
and similar): press a hotkey, send a screenshot of the shop / level-up screen,
and get advice on the best item to pick for the current build. The design is not
game-specific though — behavior is driven by swappable **profiles**, so the same
overlay can be pointed at any task by editing a text file.

> **Status:** planning. No code yet. This repo currently holds the architecture
> decisions; the MVP is the next step. See [docs/architecture-decisions.md](docs/architecture-decisions.md).

## Requirements (MVP)

0. Target environment: Linux, Omarchy (Hyprland + Wayland).
1. Overlay — an on-top panel over the foreground app.
2. LLM connection.
3. Context injection — per-task context (e.g. the game being played), actually
   injected into the request.
4. Screenshot capture, sent to the LLM automatically, with or without an
   accompanying message.
5. Show the LLM response.

## Decisions at a glance

| Decision | Choice | Why |
|---|---|---|
| Stack | Python + PyQt6 | Shortest path to a working MVP; easy to customize |
| LLM | Local LiteLLM proxy (OpenAI-compatible, `localhost:4000`) | Reuse existing routing/keys; model is just a parameter |
| Default vision model | `kimi-k2.7` (native multimodal via MoonViT) | Already exposed by the proxy; zero extra setup |
| Vision escalation | `gemini-3.5-flash` / `gemini-3.1-pro` | Add to the proxy if dense-UI reading proves weak |
| Overlay | Hotkey-summoned panel | "Just works" on Wayland with windowed/borderless games |

Full rationale, alternatives, and trade-offs for each are in
[docs/architecture-decisions.md](docs/architecture-decisions.md).

## Profiles

A profile is a text file describing one task: the system prompt / context to
inject, which model to use, and whether a screenshot is attached by default.
Customizing the overlay for a new use case means adding a profile file — no code
changes.

```
profiles/
  brotato.md        # context for Brotato builds; model: kimi-k2.7
  <your-task>.md    # anything else you want an assistant for
```
