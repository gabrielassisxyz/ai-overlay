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

> **Status:** MVP working. The core loop (capture → LiteLLM → streamed answer) and the
> Textual TUI (attachment model, in-session follow-up, `/profile` hot-reload) are done;
> the current milestone wires it to a Hyprland keybind (see
> [Hyprland setup](#hyprland-setup)). Design rationale:
> [docs/architecture-decisions.md](docs/architecture-decisions.md); behavioral contract:
> [docs/spec.md](docs/spec.md).

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
| Stack | Python + Textual (TUI) | Shortest path to a working MVP; terminal-native, easy to customize |
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

Each profile also picks its **capture mode** in `config.toml` — `fullscreen` (the focused
monitor), `active-window` (the focused window only), or `region` (drag to select with
`slurp`). See `config.example.toml`.

## Hyprland setup

The overlay is a hotkey-summoned popup: a keybind launches it in a small floating terminal,
it captures per the active profile, streams the answer, and you follow up or quit (`Esc`).
Inside the app, **`F2`** re-captures on demand (same as typing `/capture`).

Add to `~/.config/hypr/hyprland.conf` (adjust the paths, terminal, and modifier to taste):

```ini
# Launch the overlay in a dedicated terminal so the window rules can target it by class.
# Default profile:
bind = SUPER, A, exec, foot --app-id=ai-overlay uv --project ~/repositories/ai-overlay run python -m ai_overlay
# A specific profile:
bind = SUPER SHIFT, A, exec, foot --app-id=ai-overlay uv --project ~/repositories/ai-overlay run python -m ai_overlay --profile brotato

# Float, pin above fullscreen apps, center, and size the overlay terminal.
windowrulev2 = float,  class:^(ai-overlay)$
windowrulev2 = pin,    class:^(ai-overlay)$
windowrulev2 = center, class:^(ai-overlay)$
windowrulev2 = size 900 700, class:^(ai-overlay)$
```

> `foot` uses `--app-id` for the window class; for another terminal use its equivalent
> (`kitty --class ai-overlay`, `alacritty --class ai-overlay`, …) and match the class in the
> rules.

### The proxy token under a keybind

A Hyprland `exec` keybind does **not** inherit your interactive-shell environment, so the
usual `AI_OVERLAY_API_KEY` export is invisible to a keybind-launched process. Two supported
paths (both leave the token in plaintext somewhere on a single-user machine — acceptable for
a personal tool; pick per your comfort — see Decision 4 in the architecture doc):

- **Preferred — compositor env, kept out of git.** Put the token in a **gitignored** file
  you `source` from `hyprland.conf`, so every keybind child inherits it:

  ```ini
  # ~/.config/hypr/secrets.conf  (gitignored; NOT in this repo)
  env = AI_OVERLAY_API_KEY,sk-your-proxy-token
  ```
  ```ini
  # hyprland.conf
  source = ~/.config/hypr/secrets.conf
  ```

- **Fallback — raw token in the app config.** Set `api_key = "sk-..."` in
  `~/.config/ai-overlay/config.toml` (see `config.example.toml`). Self-contained, but
  plaintext in the app config — **never commit it**.
