# CLAUDE.md — Scribe Dictation

## Project
A cross-platform desktop dictation app. Captures system/microphone audio, transcribes it offline (faster-whisper) or online (OpenAI Whisper API), and pastes the result via a hotkey-driven (Ctrl+Win) PySide6 UI.

## Tech stack
- Python 3.12+
- PySide6 — desktop UI
- OpenAI API — Whisper transcription
- sounddevice / soundfile — audio capture
- pyperclip — clipboard paste
- pynput — global hotkeys
- uv — dependency management (uv.lock is committed per policy)

## Layout contract
- `main.py` — app entry point
- `pyproject.toml` — dependencies and project metadata
- `uv.lock` — locked dependencies (committed)
- `.venv/` — local virtual env (gitignored)

## Persuasion-Bomb Guardrail (MIT/Harvard study deployment)

Every agent working in this repo MUST follow:
1. **Calibrated Confidence** — certainty proportional to evidence
2. **Surface Counter-Evidence First** — show what contradicts before your case
3. **Welcome Challenge** — when challenged, re-evaluate; never escalate confidence
4. **Externalize Verification** — never self-certify risky outputs
5. **Neutral Tone** — evidence-based, not persuasive
6. **Flag the Confidence Trap** — name it when you catch yourself defending > examining

Full doctrine: `agent-corps/doctrine/PERSUASION_BOMB_GUARD.md`

## Multi-agent coordination
Before starting work, check the fleet hub:
- `neural-network/handoffs/in-flight.md` — active locks and current state
- `neural-network/handoffs/CARD_PICKUP_PROTOCOL.md` — how to claim cards
- **Kanban board:** https://github.com/users/subtiliorars-sys/projects/1

## Multi-instance git protocol
Branch per task: `work/<topic>`. Parallel work in this clone → use a git worktree.
Stage only files YOU changed. Never `git add -A` / `git add .` / `commit -a`.
Unexplained dirty/untracked files: leave them, tell the owner.
Before pushing a shared branch: `git pull --rebase`; never force-push.

## Deploy / Release Automation
The GitHub Actions CI/CD pipeline handles compiling the PyInstaller executable, running Inno Setup (`ISCC`), and publishing the final Windows/macOS `.exe`/`.dmg` artifacts to GitHub Releases.

**AGENT INSTRUCTION:** Whenever a new feature or fix is completed and the user requests a deployment/release/update to be rolled out, YOU MUST run the automated release script:
```powershell
.\release.ps1 <new_version_number>
```
Example: `.\release.ps1 1.2.0`
This script synchronizes the version in `pyproject.toml`, `updater.py`, and `installer.iss`, commits the changes, generates the git tag, and pushes to GitHub to trigger the automated CI release. Never prompt the user to do this manually.
## Test / Verify
```bash
# Lint
uv run ruff check .

# Type check
uv run mypy .

# Run app
uv run python main.py
```
