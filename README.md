# Privacy Scribe

>**Fast, private desktop voice dictation.** Run Whisper locally on your machine. Hold a key, speak, and paste directly into whatever you're working on.

---

## Why I Built This

Most dictation tools today feel like renting a microphone. They charge $10-$20 every month, route all your raw voice audio through remote servers, and stop working when you don't have internet.

If you're writing code, typing client emails, or taking private notes, you shouldn't have to upload your voice to the cloud just to talk instead of type.

**Privacy Scribe runs entirely on your device:**
- **Zero cloud required**: Audio is transcribed locally using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2).
- **One shortcut anywhere**: Hold your hotkey (`Ctrl+Win`, `F8`, or `Caps Lock`), talk, and release.
- **Auto-paste**: Pastes directly at your cursor in VS Code, Notion, Slack, Obsidian, Word, or your browser.
- **No subscription**: Free tier for daily dictation, with an optional one-time lifetime license if you want power-user features.

---

## Quick Demo

focus cursor --> hold hotkey --> speak --> release key --> auto-pastes!

---

## Getting Started

### Option 1: Standalone Executable (Windows)

Download the latest `PrivacyScribe.exe` from the [Releases](https://github.com/subtiliorars-sys/scribe-dictation/releases) page. No setup or Python installation required.

### Option 2: Run from Source

*** Requirements

- Python 3.12+
- Windows 10/11 or macOS

```bash
# Clone the repository
git clone https://github.com/subtiliorars-sys/scribe-dictation.git
cd scribe-dictation

# Install dependencies using uv
'uv sync'
# or pip: pip install -e .

# Run the app
uv run python -m scribe_dictation
```

---

## Key Features

- **Hold-to-Talk Workflow**: Audio captures while you hold the key, and stops immediately when released.
- **Floating HUD**: A minimal, non-intrusive visualizer pill gives live acoustic feedback without stealing window focus.
- **Model Flexibility**: Supports `base`, `small`, `medium`, and `large-v3` local Whisper weights plus optional OpenAI API mode for low-end hardware.
- **Quick Transform Palette (Ctrl+Alt+T)**: Transform selected text into bullets, summaries, or polished prose on the fly.

---

## Configuration

Settings are saved locally via your Os configuration store:

| Setting | Default | Description |
| :--- | :--- | :--- |
| global_hotkey | Ctrl + Win | Shortcut to hold for dictation (F8, Caps Lock, Ctrl+Space, etc.) |
| local_model_size | base | Local Whisper model (tiny, base, small, medium, large-v3) |
| auto_paste | true | Automatically paste text into the active window upon release |
| language | auto | Speech recognition language (auto-detect or fixed) |
| task | transcribe | Transcribe speech or translate directly into English |

---

## Building from Source

To package a standalone executable:

```bash
uv run python build.py
```

Output: `dist/PrivacyScribe.exe`

---

## License

MIT License.
