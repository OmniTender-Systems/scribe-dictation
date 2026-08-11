# Scribe Dictation

<p align="center">
  <img src="assets/scribe-preview.png" alt="Scribe Dictation - Windows Dictation App" width="600">
</p>

<p align="center">
  <strong>Dictate 3x faster with 100% privacy. No subscriptions. No cloud. Just works.</strong>
</p>

<p align="center">
  <a href="https://subtiliorars-sys.gumroad.com/l/eyiexi?discount=EARLY40"><img src="https://img.shields.io/badge/Get_Private_Scribe-40%25_OFF-green" alt="Get Private Scribe"></a>
  <a href="https://github.com/subtiliorars-sys/scribe-dictation"><img src="https://img.shields.io/badge/Star_on_GitHub-?_Stars-blue" alt="Star on GitHub"></a>
  <a href="https://subtiliorars-sys.gumroad.com/l/eyiexi"><img src="https://img.shields.io/badge/Buy_Now-$29-success" alt="Buy Now"></a>
</p>

---

## ?? The Problem

**Typing is slow. Cloud dictation compromises your privacy.**

You're spending hours each day typing emails, docs, code comments, and messages. Meanwhile:

- **Google Docs Voice Typing** uploads your audio to Google's servers
- **Microsoft Dictation** sends your voice data to the cloud
- **Otter.ai** costs $10/month and stores everything on their servers
- **Built-in Windows dictation** is inaccurate and requires internet

**There's a better way.**

---

## ? What Is Scribe Dictation?

Scribe Dictation is a **Windows desktop app** that turns your voice into text faster than you can type — with **100% privacy**, **no subscriptions**, and **zero cloud dependency**.

### Key Features

- ??? **100% Private Offline Mode** — Your voice never leaves your computer
- ? **Lightning-Fast Transcription** — Real-time speech-to-text using faster-whisper
- ?? **Optional Cloud Mode** — Bring your own OpenAI API key for maximum accuracy
- ?? **Global Hotkey** — Works in ANY app (VS Code, Notion, Slack, email, etc.)
- ?? **Auto-Paste** — Text appears instantly in your active window
- ?? **One-Time Payment** — $29, lifetime access, no subscriptions
- ??? **Windows Native** — Built with PySide6 for seamless Windows integration

---

## ?? Perfect For

- **Developers** — Write code, docs, and comments 3x faster
- **Writers & Bloggers** — Draft content without carpal tunnel
- **Productivity Enthusiasts** — Optimize your workflow
- **Privacy-Conscious Users** — Refuse to upload voice data to the cloud
- **Anyone with RSI** — Reliable dictation for typing difficulties

---

## ?? Quick Start

### Option 1: Download the App (Easiest)

**Buy Private Scribe for $29:**
?? [https://subtiliorars-sys.gumroad.com/l/eyiexi](https://subtiliorars-sys.gumroad.com/l/eyiexi?discount=EARLY40)

**Use code `EARLY40` for 40% off** (first 20 customers only)

Download includes:
- `PrivateScribe.exe` — standalone Windows app (no installation required)
- Lifetime license key
- Free updates forever

### Option 2: Run from Source (Developers)

#### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Windows 10/11

#### Installation

```bash
# Clone the repo
git clone https://github.com/subtiliorars-sys/scribe-dictation.git
cd scribe-dictation

# Install dependencies
uv sync

# Run the app
uv run python main.py
```

---

## ?? Documentation
### UI Layout

The interface is built using **PySide6** with a clean, single-window design:

```
+---------------------------------------------------+
¦ File  Help                                        ¦
+---------------------------------------------------¦
¦                                                   ¦
¦  Transcribed text will appear here...            ¦
¦                                                   ¦
¦                                                   ¦
+---------------------------------------------------¦
¦  [ ?? Mic Record ]   [ ?? Copy ]  [ ??? Clear ]   ¦
+---------------------------------------------------¦
¦ Status: Idle / Recording... / Transcribing...     ¦
+---------------------------------------------------+
```

### Keybindings

- **Global Hotkey: `Ctrl+Win`**
  - *Hold to Talk*: Press and hold to record, release to transcribe
  - *Tap to Toggle*: Briefly press to toggle-lock recording on/off

- **App-Specific Shortcuts** (when window is focused):
  - `Ctrl+R` — Toggle recording
  - `Ctrl+,` — Open Settings
  - `Ctrl+Q` — Quit app

### Configuration

The app uses `PySide6.QtCore.QSettings` for persistent configuration:

| Setting | Default | Description |
|---------|---------|-------------|
| `use_local` | `"true"` | `"true"` for offline mode, `"false"` for OpenAI API |
| `api_key` | `""` | OpenAI API key (required if `use_local` is `"false"`) |
| `local_model_size` | `"base"` | Model size: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `audio_device` | `""` | Input device index (empty = system default) |
| `auto_paste` | `"true"` | Auto-paste transcribed text into active window |

---

## ?? GPU Acceleration (Optional)

For faster transcription, enable CUDA acceleration:

### Prerequisites

- NVIDIA GPU (Compute Capability 5.0+)
- CUDA Toolkit 12.x
- cuDNN v8 or v9

### Setup

1. **Install CUDA Toolkit** from [NVIDIA CUDA Toolkit Archive](https://developer.nvidia.com/cuda-toolkit-archive)
2. **Install cuDNN** from [NVIDIA cuDNN Archive](https://developer.nvidia.com/cudnn)
3. **Install PyTorch with CUDA:**
   ```bash
   uv pip install torch --index-url https://download.pytorch.org/whl/cu121 --force-reinstall
   ```
4. **Verify CUDA:**
   ```bash
   uv run python -c "import torch; print('CUDA available:', torch.cuda.is_available())"
   ```
5. **Run the app** and select **Local (faster-whisper) - Offline** mode in Settings

If CUDA is unavailable, the app automatically falls back to CPU execution.

---

## ?? Building from Source

### Build the Executable

```bash
# Build standalone executable
uv run python build.py
```

Output: `dist/PrivateScribe.exe`

---

## ?? Comparison: Private Scribe vs. Alternatives

| Feature | Private Scribe | Google Docs | Otter.ai | Microsoft Dictation |
|---------|---------------|-------------|----------|---------------------|
| **100% Offline** | ? | ? | ? | ? |
| **One-Time Payment** | ? ($29) | ? (Free) | ? ($10/mo) | ? (Free) |
| **Privacy First** | ? | ? | ? | ? |
| **No Account Required** | ? | ? | ? | ? |
| **Global Hotkey** | ? | ? | ? | ? |
| **Auto-Paste** | ? | ? | ? | ? |
| **Windows Native** | ? | ? | ? | ? |

---

## ?? Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## ?? License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## ?? Support

If this project helps you, please consider:

- ? **Starring the repo** — helps others find it
- ?? **Sharing on Twitter** — spread the word
- ?? **Joining the discussion** — open an issue or PR
- ?? **Buying a license** — support development and get the app

<p align="center">
  <strong>Built with ?? for privacy-conscious developers and writers</strong>
</p>

---

## ?? Related Projects

- **[Fleet Health Dashboard](https://github.com/subtiliorars-sys/fleet-health)** — Monitor all your services in one place
- **[Multi-Agent Fleet Field Guide](https://subtiliorars-sys.gumroad.com/l/ixrsyx?discount=LAUNCH50)** — Scale your AI-assisted workflow

