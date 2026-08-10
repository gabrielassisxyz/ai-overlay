# SPEC — ai-overlay MVP

**What this doc is:** the *behavioral contract*, stating what each piece must do precisely enough that any agent implementing a slice has one source of truth instead of inferring from prose. It is **living**: update it when a milestone teaches something new.

**What it is NOT** (to avoid three docs saying the same thing):
- *How to work here* (commands, TDD, security, git) lives in [`../AGENTS.md`](../AGENTS.md).
- *Why the stack / LLM / overlay were chosen* lives in [`architecture-decisions.md`](architecture-decisions.md).
- This file owns the *what*: schemas, surfaces, and error semantics. When they disagree, this file is authoritative for behavior.

---

## 1. Summary

A hotkey-summoned Textual TUI that captures the screen, sends it to an LLM (via the local LiteLLM proxy) with a per-task profile prompt injected, and streams the answer back — with in-session follow-up. "Advise on my build/deck" and "answer a question about what's on screen" are the same mechanism; only the profile's prompt differs.

---

## 2. Config contract

- **Location:** `~/.config/ai-overlay/config.toml`.
- **API key:** the proxy holds the real vendor keys; the app needs only a token for the proxy. Precedence: `api_key` (raw, in config) > `api_key_env` (name of an env var to read) > the env chain `AI_OVERLAY_API_KEY` → `OPENAI_API_KEY` > a placeholder (keyless proxy). A raw `api_key` is the only option that also works for a Hyprland keybind launch (which inherits no shell env), but it sits in plaintext — so **don't commit a config that contains it**; `config.example.toml` never does.

### Global keys

| Key | Default | Meaning |
|---|---|---|
| `default_profile` | *(required)* | Profile used when `--profile` is omitted. |
| `base_url` | `http://localhost:4000/v1` | LiteLLM endpoint. Only host the app talks to. |
| `model` | `kimi-k2.7` | Default model; a profile may override it. |
| `max_image_width` | `1280` | Screenshot is downscaled to this width before sending (cost + exposure). |
| `auto_capture` | `true` | `true`: the TUI captures + sends on launch (summon-and-ask). `false`: it opens idle; stage a shot with `/capture`. |
| `api_key` | *(unset)* | Raw proxy token. Works for keybind launch, but plaintext — never commit it. |
| `api_key_env` | *(unset)* | Name of an env var to read the token from, instead of the default chain. |

### Per-profile block `[profiles.<name>]`

| Key | Default | Meaning |
|---|---|---|
| `system_prompt_file` | *(required)* | Path (`~` expanded) to the `.md` prompt injected as the system message. |
| `capture` | `fullscreen` | `fullscreen` \| `active-window` \| `region`. |
| `model` | *(inherit global)* | Optional per-profile model override. |

### Resolution rules

- Active profile = `--profile <name>` if given, else `default_profile`.
- Unknown profile name → exit with a clear error that **lists the available profiles**. Never fall back silently.
- Missing `system_prompt_file` on disk → clear error naming the path.

---

## 3. Capture contract

`capture(mode) -> PNG bytes`, via subprocess (tools ship with Omarchy):

| Mode | How |
|---|---|
| `fullscreen` | the **focused monitor only**: `hyprctl monitors -j` (pick `focused`) → `grim -o <name> -`. |
| `active-window` | `hyprctl activewindow -j` geometry → `grim -g "<geom>" -`. |
| `region` | `slurp` (user drags) → `grim -g "<geom>" -`. |

- Downscale to `max_image_width` before returning (Pillow), re-encode PNG, then base64 for the LLM message.
- **Privacy:** image bytes are never logged and never written to disk outside a temp path the user controls. Downscale happens before anything leaves the process.
- The subprocess runner is injected so tests use a named fake — **tests never call real `grim`/`slurp`/`hyprctl`.**

---

## 4. LLM contract

- OpenAI-compatible `openai` client, `base_url` from config, key from env (§2). **Only** talks to `base_url` (localhost). Any change adding a direct-vendor call or a new outbound host must be flagged.
- Messages: `system` = the profile prompt; `user` = optional text + the image as an `image_url` with a base64 `data:` URL.
- `stream_reply(messages) -> Iterator[str]` yields text deltas as they arrive.
- **Errors fail loudly, actionably:** proxy unreachable / non-2xx → a message that names the likely cause ("is the LiteLLM proxy running on localhost:4000?"), not a raw traceback swallowed silently.
- The `openai` client is injected so tests use a fake — **tests never hit the network.**

---

## 5. Interaction contract (TUI — Milestone B)

The interaction is an **attachment** model: a screenshot is staged as a *pending attachment* and sent together with your message. Each send builds the payload as `[system(active profile)] + history + turn` — the current profile's prompt leads every call.

- **Launch:** `python -m ai_overlay [--profile <name>] [initial question...]`, wired to a Hyprland keybind; a Hyprland window rule floats + pins the terminal.
  - `auto_capture = true` (default): capture per the active profile's mode and send immediately — with the initial question if given, else profile-only (summon-and-ask).
  - `auto_capture = false`: open idle. Nothing is captured or sent until the user stages a shot with `/capture` and sends a message.
- **Message:** plain text in the input box sends a turn — with the pending screenshot if one is staged, else text-only — and continues the same conversation. A message with no freshly staged shot does **not** re-capture (a plain follow-up).
- **Commands** (only a leading `/` is parsed — this is *not* a general command framework; the commands are `/profile` and `/capture`):
  - `/capture` → (re)capture per the active profile's mode and stage the image for the next message. This is the on-demand / re-look path. *(A screenshot hotkey that does this without typing `/capture` is Milestone C.)*
  - `/profile` → list available profiles, marking the active one.
  - `/profile <name>` → **hot-reload** the active profile. Past turns are not rewritten, but the leading system message and model are rebuilt from the new profile on the next send; a short transition note is prepended to that message so the model has an explicit pivot. Does not re-capture on its own.
- **Quit:** `Esc` or `Ctrl+C`.

---

## 6. Milestones & acceptance

- **A — core loop, no TUI.** `config` + `capture` + `llm` wired into a one-shot that streams the answer to stdout for the default (or `--profile`) profile. *Done when:* running it captures, calls the proxy, and streams a real answer; `config`/`capture`/`llm` unit-tested with fakes; `bin/ci` green.
- **B — the MVP.** Textual TUI over A: streaming answer pane, input box, the attachment model (`/capture` stages a shot sent with the next message; `auto_capture` gates the launch shot), in-session follow-up, `default_profile` + `/profile` (hot-reload). *Done when:* summon → ask → read → follow-up → `/capture` re-look → `/profile` switch → quit works end-to-end; `run_test` pilots pass; `bin/ci` green.
- **C — widen.** `active-window` + `region` capture modes; a second real profile; the Hyprland keybind + float window-rule documented in the README. *Done when:* all three capture modes exercised by tests; docs updated.

---

## 7. Out of scope (YAGNI — flag if a change drifts here)

`wlr-layer-shell` overlay, always-on HUD, exclusive-fullscreen coverage, voice input, a persistent daemon, a general slash-command framework, provider abstraction (the proxy already provides it). The **screenshot hotkey** that stages a `/capture` without typing it is Milestone C, not B.
