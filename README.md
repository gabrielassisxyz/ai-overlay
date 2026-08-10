# ai-overlay

[![ci](https://github.com/gabrielassisxyz/ai-overlay/actions/workflows/ci.yml/badge.svg)](https://github.com/gabrielassisxyz/ai-overlay/actions/workflows/ci.yml)

A generic, customizable AI assistant overlay for Linux (Hyprland / Wayland).

Summon a panel over whatever you're doing, optionally grab a screenshot, send it to an LLM with task-specific context injected, and read the answer — without alt-tabbing out of the foreground app.

The first target use case is **games** (Brotato, Bounty of One, Vampire Survivors and similar): press a hotkey, send a screenshot of the shop / level-up screen, and get advice on the best item to pick for the current build. The design is not game-specific though — behavior is driven by swappable **profiles**, so the same overlay can be pointed at any task by editing a text file.

> **Status:** MVP working end to end. The core loop (capture → LiteLLM → streamed answer), the Textual TUI (attachment model, in-session follow-up, `/profile` hot-reload) and the Hyprland keybind launch (see [Hyprland setup](#hyprland-setup)) are all in place. What is still missing, and what is deliberately out of scope, is in [ROADMAP.md](ROADMAP.md). Design rationale: [docs/architecture-decisions.md](docs/architecture-decisions.md); behavioral contract: [docs/spec.md](docs/spec.md).

## This repository is the shared core

Two applications are being built on top of it, each getting a repository of its own:

- **[wisp-assistant](https://github.com/gabrielassisxyz/wisp-assistant)**, the general case: ask an LLM about whatever happens to be on screen. *That repository does not exist yet, so the link is dead for now.*
- **grimoire**, for games, where the advice comes from a catalogue, tracked run state and a ranker rather than from a prompt alone. *Also not created yet.*

The core owns what both of them need: screen capture, the LLM client, settings, and the summoned overlay shell. Both leaves are summoned overlays, so the shell is shared and only the view differs; neither leaf depends on the other.

That boundary is provisional on purpose. If the `wlr-layer-shell` panel gets built, a shared repository earns its keep. If it never does, the core stays small enough to be absorbed into `wisp-assistant`, leaving `grimoire` to copy the two modules it actually uses.

The extraction has not happened yet. What is in this repository today is the whole working tool, TUI and example profiles included, which is what the rest of this README describes.

## Install

You need Linux with a Wayland compositor (developed against Hyprland), [`uv`](https://docs.astral.sh/uv/), and the `grim` and `slurp` capture tools. Most Wayland distributions package the latter two; on Arch they are `pacman -S grim slurp`.

You also need an **OpenAI-compatible endpoint that serves a multimodal model**. The reference setup is a local [LiteLLM proxy](https://docs.litellm.ai/docs/simple_proxy), which holds the vendor keys so this app never has to: it talks to the proxy and nothing else. Any other OpenAI-compatible endpoint works too, as long as `base_url` points at it.

```sh
git clone https://github.com/gabrielassisxyz/ai-overlay
cd ai-overlay
uv sync

# The app reads its config and prompts from ~/.config/ai-overlay, never from the clone,
# so the two files below have to be copied out of it once.
mkdir -p ~/.config/ai-overlay/profiles
cp config.example.toml ~/.config/ai-overlay/config.toml
cp profiles/*.md ~/.config/ai-overlay/profiles/
```

Now open `~/.config/ai-overlay/config.toml` and set two things:

- **`model`**, to something your endpoint actually serves. The shipped default `kimi-k2.7` is an example, not a guarantee: if your proxy does not expose it, every call fails with a model-not-found error.
- **the proxy token**, if your endpoint needs one. `AI_OVERLAY_API_KEY` in the environment is enough for a shell launch; a keybind launch needs one of the two paths in [The proxy token](#the-proxy-token-under-a-keybind).

Check it works before wiring any keybind:

```sh
uv run python -m ai_overlay --print "what is on screen?"
```

That captures the focused monitor, sends it, and streams the answer to stdout. Once it answers, wire the keybind below.

## Requirements (MVP)

0. Target environment: Linux, Omarchy (Hyprland + Wayland).
1. Overlay — an on-top panel over the foreground app.
2. LLM connection.
3. Context injection — per-task context (e.g. the game being played), actually injected into the request.
4. Screenshot capture, sent to the LLM automatically, with or without an accompanying message.
5. Show the LLM response.

## Decisions at a glance

| Decision | Choice | Why |
|---|---|---|
| Stack | Python + Textual (TUI) | Shortest path to a working MVP; terminal-native, easy to customize |
| LLM | Local LiteLLM proxy (OpenAI-compatible, `localhost:4000`) | Reuse existing routing/keys; model is just a parameter |
| Default vision model | `kimi-k2.7` (native multimodal via MoonViT) | An example default, not a requirement; any multimodal model your endpoint serves works |
| Vision escalation | a stronger vision model, per profile | Set `model` on the profile if dense-UI reading proves weak |
| Overlay | Hotkey-summoned panel | "Just works" on Wayland with windowed/borderless games |

Full rationale, alternatives, and trade-offs for each are in [docs/architecture-decisions.md](docs/architecture-decisions.md).

## Profiles

A profile is a text file describing one task: the system prompt / context to inject, which model to use, and whether a screenshot is attached by default. Customizing the overlay for a new use case means adding a profile file — no code changes.

```
profiles/
  brotato.md        # context for Brotato builds; model: kimi-k2.7
  <your-task>.md    # anything else you want an assistant for
```

Each profile also picks its **capture mode** in `config.toml` — `fullscreen` (the focused monitor), `active-window` (the focused window only), or `region` (drag to select with `slurp`). See `config.example.toml`.

## Hyprland setup

The overlay is a hotkey-summoned popup: a keybind launches it in a small floating terminal, it captures per the active profile, streams the answer, and you follow up or quit (`Esc`). Inside the app, **`F2`** re-captures on demand (same as typing `/capture`).

Add to `~/.config/hypr/hyprland.conf`, replacing `/path/to/ai-overlay` with wherever you cloned it (and adjusting the terminal and modifier to taste):

```ini
# Launch the overlay in a dedicated terminal so the window rules can target it by class.
# Default profile:
bind = SUPER, A, exec, foot --app-id=ai-overlay uv --project /path/to/ai-overlay run python -m ai_overlay
# A specific profile:
bind = SUPER SHIFT, A, exec, foot --app-id=ai-overlay uv --project /path/to/ai-overlay run python -m ai_overlay --profile brotato

# Float, pin above fullscreen apps, center, and size the overlay terminal.
windowrulev2 = float,  class:^(ai-overlay)$
windowrulev2 = pin,    class:^(ai-overlay)$
windowrulev2 = center, class:^(ai-overlay)$
windowrulev2 = size 900 700, class:^(ai-overlay)$
```

> `foot` uses `--app-id` for the window class; for another terminal use its equivalent (`kitty --class ai-overlay`, `alacritty --class ai-overlay`, …) and match the class in the rules.

### The proxy token under a keybind

A Hyprland `exec` keybind does **not** inherit your interactive-shell environment, so the usual `AI_OVERLAY_API_KEY` export is invisible to a keybind-launched process. Two supported paths (both leave the token in plaintext somewhere on a single-user machine — acceptable for a personal tool; pick per your comfort — see Decision 4 in the architecture doc):

- **Preferred — compositor env, kept out of git.** Put the token in a **gitignored** file you `source` from `hyprland.conf`, so every keybind child inherits it:

  ```ini
  # ~/.config/hypr/secrets.conf  (gitignored; NOT in this repo)
  env = AI_OVERLAY_API_KEY,sk-your-proxy-token
  ```
  ```ini
  # hyprland.conf
  source = ~/.config/hypr/secrets.conf
  ```

- **Fallback — raw token in the app config.** Set `api_key = "sk-..."` in `~/.config/ai-overlay/config.toml` (see `config.example.toml`). Self-contained, but plaintext in the app config — **never commit it**.
