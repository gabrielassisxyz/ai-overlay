# ai-overlay — Agent Briefing

> Read before every interaction. Living spec: short, imperative. On every gotcha or decision, append one line here. The `universal-principles` block below is generated from a single canonical source: re-sync it there, never edit it in place.

> **What it is:** a hotkey-summoned AI assistant panel for Linux (Hyprland / Wayland) — screenshot the foreground app, send it to an LLM via a local LiteLLM proxy with a per-task profile injected, read the answer. Task behavior is driven by `profiles/*.md`.

> **Calibration:** Tier 2 · Phase: work. External stakes are contained (local-only, no hosted service, no third-party data); personal stakes are high, since this is a public developer tool meant to grow. **Review gate:** standard. One independent opinion over the whole branch diff, exactly once, pre-push. No per-commit reviews.

## Stack & Commands
- **Stack:** Python (uv-managed, `.python-version` = 3.13) + Textual TUI (floating terminal, MVP surface) + OpenAI-compatible `openai` client → local LiteLLM proxy (`http://localhost:4000/v1`, streaming, multimodal). A `wlr-layer-shell` GTK4 overlay is a deliberate later phase, not the MVP. See [docs/spec.md](docs/spec.md) for the behavioral contract (config schema, capture / LLM / TUI surface, error semantics) and [docs/architecture-decisions.md](docs/architecture-decisions.md) for the why.
- **Setup:** `uv sync` (creates `.venv` with dev tools) then `bin/install-hooks` (once).
- **Run:** `uv run python -m ai_overlay [--profile <name>] [question]` launches the TUI; add `--print` for the headless one-shot (streams the answer to stdout, no TTY).
- **Test:** `uv run pytest`.
- **All CI checks:** `bin/ci` (ruff format + lint, pytest, pip-audit, litellm-proxy reachability probe, soft-wrap check, prose gate). The proxy probe warns `SKIPPED` rather than failing where the proxy cannot exist, such as GitHub Actions.
- **Sandbox (optional):** `ai-jail claude` runs the agent OS-fenced (project read-write, host read-only, `~/.ssh`/`~/.gnupg`/`~/litellm` unreachable, `.env` masked) — pair it with dangerous permissions, e.g. `ai-jail claude --dangerously-skip-permissions`. Config: `.ai-jail`.

## Scope (current)
- **Current scope:** planning-stage MVP — a personal, local-only hotkey-summoned TUI that captures the screen and asks the LLM about it. Two framings — "advise on my build/deck" and "answer a question about what's on screen" — are the SAME mechanism: capture + a per-task profile prompt → a streamed answer, with in-session follow-up. Profiles are TOML blocks in `~/.config/ai-overlay/config.toml` pointing at prompt files under `profiles/*.md`; each profile sets its capture mode (fullscreen / active-window / region). Invocation is a Hyprland keybind calling the entrypoint with `--profile`.
- Don't expand beyond it without a present need: no persistent/always-on HUD, no `wlr-layer-shell` overlay yet (deliberate later phase), no exclusive-fullscreen support, no voice, no text-only-without-capture mode, no provider abstraction (the proxy already gives that). If a change drifts past it, STOP and flag it.

<!-- BEGIN universal-principles v3 -->
## Working principles

- **The human defines the WHAT; the agent decides the HOW.** Don't wait for line-by-line dictation. Plan first for non-trivial tasks: show the plan + to-do list, wait for approval.
- **Think before coding — don't assume, don't hide confusion.** State assumptions explicitly; if multiple interpretations exist, present them — don't pick silently. If a simpler approach exists, say so and push back. If a task is impossible under the stated constraints, or info is missing, say so — don't guess. (For trivial tasks, use judgment; this is bias, not ritual.)
- **Surgical changes — touch only what you must.** Every changed line traces to the task. Don't "improve" adjacent code, reformat, or refactor what isn't broken; match existing style even if you'd do it differently. Flag unrelated dead code — don't delete it. Remove only the imports / variables / functions your own change orphaned.
- **Chesterton's Fence — find the problem before undoing the decision.** A config, a flag, a workaround that looks arbitrary is a **fence**: someone put it there, probably to fix something that is invisible to you *because the fence is working*. You arrive with no history, so absence of a visible reason is evidence of your ignorance, not of its uselessness. When your fresh measurement contradicts what the human vaguely remembers ("I changed this once, because of some problem"), **your measurement is the suspect first** — it may be measuring the case that *isn't* failing. Go find the original problem, then decide. *(A CIFS share was benchmarked with a big sequential `dd`, looked fast, and the local-disk download dir was "fixed" away — while the actual failure was random writes: par2, unrar, torrent piece-writes. Two wrong commits.)*
- **Goal-driven execution — define the success check, then loop to it.** Turn the task into something verifiable before coding: "add validation" → write tests for invalid inputs, then pass them; "fix the bug" → write a failing repro test, then pass it; "refactor X" → tests green before and after. For multi-step work, state a brief plan with a verify step each.
- **"Flaky" is not a diagnosis — test in the environment the thing actually runs in.** A component that fails *consistently* under automation is being **mis-invoked**, not being unreliable; "it works when I run it by hand" is not evidence that it works. The shell you test in has a TTY, a `$HOME`, an `ssh-agent`, an interactive stdin — the systemd unit, the CI job and the scripted harness have none of those, so a passing manual run can be testing a different program. Reproduce it *there* (start the unit, `env -u SSH_AUTH_SOCK`, `</dev/null`, `--dry-run` to print the real command line) before accepting "unstable" as a cause. **When a fix doesn't change the symptom, stop fixing and go look at what is actually being executed.** *(An interactive-mode flag with no TTY made one harness fail every review panel for weeks, written off as "flaky"; it was the wrong flag.)*
- **KISS — don't solve a problem you don't have yet.** Simplicity isn't "write less code"; it's not building for a need that doesn't exist. Let structure emerge from the code.
- **YAGNI & flat.** No preventive abstractions, no single-use interfaces. Interfaces for real boundaries only. Architecture is *extracted* once a pattern proves itself in real use — never designed up front for a user who doesn't exist yet. Need pulls architecture.
- **Order: make it work → make it right → make it fast** (Kent Beck), in that order. Most over-engineering is doing "right"/"fast" before a working thing exists to justify it.
- **Flag scope creep — a standing duty, not a suggestion.** When a solo tool starts being framed as a public / multi-user / multi-tenant / plugin-system / configurable-N-backends platform before a real, present need exists, STOP and ask: "Is this needed now?" Justify future-proofing against a need that exists *today*.
- **No silent decisions (comprehension debt).** Never make a silent architectural or design call — state it and record the rationale, so the reasoning is recoverable later.
- **Real decisions are presented in the chat, in isolation — never via popup.** When a design/architecture/scope/trade-off decision arises, surface it on its own: the options, what each means, pros/cons/trade-offs, and a recommendation — then decide together. Don't bury it mid-text or bundle it with other topics, and don't compress it into a quick-pick widget (e.g. AskUserQuestion) — the widget skips the reasoning and overlays the explanation. Widgets are for trivial short-answer picks only.
- **Long answers are written to be scanned, not read twice.** For recaps, status reports, batch reviews, plans, and any comparison of options: lead with the outcome in one line, then break the body into bullets and **bold** the load-bearing terms. Options are always a list — one bullet per option, the recommended one marked — never a paragraph the reader has to parse to find the choices. Reserve unbroken prose for short arguments; a wall of paragraphs costs more in re-reading than the structure would have cost in words.

## Git: branches, commits, PRs, comments

- **Ask the repo for its default branch; never assume one.** Repos differ — `master` and `main` are both common, often in the same person's account — and a wrong guess sends a PR to a branch that does not exist, or, worse, has you "fixing" a URL that was right all along. `git symbolic-ref --short refs/remotes/origin/HEAD | sed 's|^origin/||'`, or `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`. Never commit directly to it: branch, then PR.
- **A new repo starts on `main`.** That is the preferred name, and `init.defaultBranch` is set to it, so `git init` produces it without anyone choosing. It settles new repos only: an existing one keeps the branch it has, because renaming breaks open PRs, CI filters, deploy hooks and every permalink into the tree, and buys nothing. The rule above still governs everything already in existence — ask, never assume.
- **Branches** — Conventional Branch (conventionalbranch.org): `<type>/<kebab-description>`, types `feature/`, `bugfix/`, `hotfix/`, `chore/`, `release/`, `docs/`.
- **Commits** — Conventional Commits (conventionalcommits.org): `<type>(scope): <description>`, types `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `build`, `perf`, `style`. Breaking change → `!` after the type or a `BREAKING CHANGE:` footer.
- **Atomic commits** — one logical change per commit, each independently green and revertible. Never `git add .` blind; split unrelated changes.
- **Always work in your own worktree — mandatory, not conditional.** Parallel sessions are opened freely and nothing signals their existence to you, so a "check whether another session is here first" step can never be reliable — the honest answer is always "maybe". The only collision-proof arrangement is structural: keep the main working tree on the default branch as a clean reference and **never work in it** — before your first write (commit, branch, rebase, stash; read-only exploration is exempt), create your own worktree and do everything there: `git worktree add ../<repo>-<task> -b <your-branch> <origin>/<default-branch>`. Do this **whether or not** you believe another agent is running — that belief is exactly what you cannot verify. Report which worktree/branch you used; remove it once merged. Only the human can see all the open sessions.
- **Pull requests** — describe **what + why**. *What*: a 1–3 line summary. *Why* (the bulk): decisions, trade-offs, rejected alternatives. The diff shows the what; the PR explains why.
- **Comments** — always **WHY, not WHAT**: explain intent, never restate the obvious mechanics. Keep existing comments; they carry intent.

## Code style (baseline)

- Functions: 4–40 lines, one thing each (SRP). Files: under ~500 lines, split by responsibility.
- Names specific and unique — avoid `data`, `handler`, `Manager`, `util`.
- Explicit types. Early returns over nested ifs; max ~2 levels of indentation.
- Inject dependencies; wrap third-party libs behind a thin interface this project owns.
- No duplication — but don't extract *too early*. Tolerate duplication while the pattern is still forming; extract the abstraction *from* proven, repeated code, never ahead of it.
- **Refactoring is not automatic.** After a large feature, list refactoring candidates (files > ~500 lines, duplicated logic, long functions, hardcoded config) and ask before pruning — the human decides, the tests are the safety net. Consolidate when the thing works and the seams are obvious, not before.
<!-- END universal-principles v3 -->

## Tests (TDD)
- Every feature is born with a test; every bugfix with a regression test.
- Tests run with ONE command (`uv run pytest`), no manual setup, no real network/proxy — mock the LLM call and `grim` with a named fake. If it can't run headless, it's wrong.
- Before saying "done", run `bin/ci` and show the result.

## Small releases
- Every commit on `master` passes `bin/ci` and is runnable — no "broken commit I fix in the next one". Branch off `master`, PR back (conventions are in the global config).
- If I forget to commit closed work before switching tasks, remind me.

## Security (habit, not a phase)
- Screenshots can capture anything on screen — never log image bytes or write them to disk outside a temp path the user controls; downscale before sending (cost + exposure).
- The LiteLLM proxy holds the keys; this app must not embed any API key. Talk only to `localhost:4000`. Flag any change that adds a direct-vendor call or a new outbound host.
- Dependency CVEs are caught by `pip-audit` in `bin/ci` / CI.

## Git & secrets
- Before any commit, show `git status` + `git diff --cached`; confirm no secret is staged. The gitleaks pre-commit hook is the deterministic backstop; this habit is the probabilistic one. Run `bin/install-hooks` once per clone so the hook is active.
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
- The prose gate runs in `--diff` mode against `origin/master`, so text written before the gate existed is left alone and only new lines are judged. Override the base with `SLOP_GUARD_BASE` when a branch forks from somewhere else.
- Runtime deps are declared in `pyproject.toml` only once code imports them, so the harness carries only what is in use.
- The TUI runs in a floating terminal — launch it under a dedicated class (`foot --app-id=ai-overlay`) and float/pin/center it with `windowrulev2 = ..., class:^(ai-overlay)$` (pinned in README "Hyprland setup"). The later `wlr-layer-shell` overlay (GTK4 + gtk4-layer-shell) is what will draw above fullscreen; don't reach for it until the TUI MVP proves the idea.
- The LiteLLM proxy must be running for the app to work; a failed call should say so loudly.
- The API key comes only from env (`AI_OVERLAY_API_KEY` → `OPENAI_API_KEY`); the proxy rejects the `sk-noop` placeholder. A Hyprland-keybind `exec` does NOT inherit your interactive shell env — **resolved in Milestone C** (architecture-decisions Decision 4): put the token in the compositor env via a gitignored Hyprland `source`d `env =` include (preferred), or set a raw `api_key` in the app config (fallback). See README "Hyprland setup". Never commit the key.
