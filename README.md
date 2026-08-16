# Scribe Dictation

A modern, privacy-focused desktop dictation application for Windows. It captures microphone audio, transcribes it offline locally via `faster-whisper` (CPU/GPU) or online via the OpenAI Whisper API, and automatically copies and pastes the result directly into your active window.

[**Get Lifetime License on Gumroad (https://gumroad.com/l/eyiexi)**](https://gumroad.com/l/eyiexi)

---

## 1. UI Layout Guidelines

The interface is built using **PySide6** and follows a clean, single-window design optimized for accessibility and status visibility:

```
+───────────────────────────────────────────────────+
| File  Help                                        |
+───────────────────────────────────────────────────+
|                                                   |
|  Transcribed text will appear here...             |
|                                                   |
|                                                   |
+───────────────────────────────────────────────────+
|  [ 🎤 Record ]   [ 📋 Copy ]   [ 🗑 Clear ]        |
+───────────────────────────────────────────────────+
| Global Hotkey: Hold Ctrl + Win to record, release |
| Status: Idle / Recording... / Transcribing...      |
+───────────────────────────────────────────────────+
```

### Visual Components & Spacing
*   **Main Window**: Minimum dimensions configured to `480x360` pixels for compact readability.
*   **Central Widget Layout**: A `QVBoxLayout` with `12px` margins and `8px` spacing.
*   **Text Editor (`QPlainTextEdit`)**: Read-only display buffer for transcriptions.
*   **Control Panel (`QHBoxLayout`)**:
    *   **Record Button**: Expanding push button (`40px` minimum height). Toggles status/recording.
    *   **Copy Button**: Copies transcribed text to clipboard.
    *   **Clear Button**: Resets text box and status.
*   **Status Bar**: Located at the bottom to report app states: `Idle`, `Recording...`, `Transcribing...`, `Done`.
*   **System Tray Integration**: Background running capabilities with context options for quick toggles, settings, and quitting.

---

## 2. Configuration Setup

The application uses `PySide6.QtCore.QSettings` for persistent configuration.

### Configuration Storage Paths
*   **Windows**: Stored in the registry at:
    `HKEY_CURRENT_USER\Software\ScribeDictation\Scribe Dictation`
*   **macOS**: `~/Library/Preferences/com.ScribeDictation.Scribe Dictation.plist`
*   **Linux**: `~/.config/ScribeDictation/Scribe Dictation.conf`

### Configuration Keys & Settings
| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `use_local` | string | `"true"` | `"true"` for local offline faster-whisper transcription; `"false"` for OpenAI API. |
| `api_key` | string | `""` | OpenAI API key (`sk-...`). Required if `use_local` is `"false"`. |
| `local_model_size` | string | `"base"` | Model size for local execution (`tiny`, `base`, `small`, `medium`, `large-v3`). |
| `audio_device` | string | `""` | Selected input device index (from sounddevice). Empty uses system default. |
| `auto_paste` | string | `"true"` | Auto-pastes transcribed text into active cursor window. |
| `play_sounds` | string | `"true"` | Plays tactile retro tape deck mechanical punch sounds on record start/stop. |
| `global_hotkey` | string | `"Ctrl + Win"` | Configured global push-to-talk hotkey combination. |

---

## 3. User Instructions & Keybindings

### Prerequisites & Running
Install dependencies using `uv` (recommended) or standard `pip`:
```bash
# Install package dependencies
uv sync

# Run Scribe Dictation
uv run python main.py
```

### Keybindings (Keyboard Shortcuts)
The application utilizes both global and application-specific keyboard shortcuts:

*   **Global Hotkey: `Ctrl+Win` (Windows/Linux) or `Ctrl+Cmd` (macOS)**
    *   *Hold to Talk*: Press and hold the keys to record; release them to stop recording and begin transcribing.
    *   *Tap to Toggle*: Briefly press (less than 0.4 seconds) and release to toggle-lock recording on. Press `Ctrl+Win` again to stop.
*   **Application-Specific Shortcuts** (Active only when the Scribe Dictation window is focused):
    *   `Ctrl+R`: Toggle recording on/off.
    *   `Ctrl+,`: Open Settings dialog.
    *   `Ctrl+Q`: Exit application.

### Auto-Silence Detection
The application actively monitors background levels. If incoming audio levels drop below the threshold (`0.01` RMS) for `1.5` seconds, the recording stops automatically and initiates transcription.

---

## 4. CUDA & GPU Acceleration Setup

To achieve fast, real-time transcription locally using `faster-whisper`, GPU acceleration via NVIDIA CUDA is highly recommended.

### Step-by-Step CUDA Setup (Windows/Linux)

Local offline transcription is powered by `ctranslate2`, which requires specific NVIDIA libraries.

#### Step 1: Verify Hardware Compatibility
Ensure you have a CUDA-compatible NVIDIA GPU (Compute Capability 5.0 or higher is required).

#### Step 2: Install CUDA Toolkit & cuDNN
1.  **CUDA Toolkit**: Download and install **CUDA Toolkit 12.x** (or **11.x** depending on your PyTorch build compatibility) from [NVIDIA CUDA Toolkit Archive](https://developer.nvidia.com/cuda-toolkit-archive).
2.  **cuDNN**: Download the corresponding version of **cuDNN v8 or v9** from the [NVIDIA cuDNN Archive](https://developer.nvidia.com/cudnn).
3.  **Path Configuration**: Extract the cuDNN files and place the DLLs (`cublas64_12.dll`, `cudnn_ops_infer64_8.dll`, etc.) in a directory added to your system `PATH`, or copy them directly into the root folder of your virtual environment `.venv/Scripts/`.

#### Step 3: Install PyTorch with CUDA Support
By default, standard package installation may fetch CPU-only wheels. Force pip/uv to install the CUDA-supported version of PyTorch:
```bash
# For CUDA 12.1 compatibility
uv pip install torch --index-url https://download.pytorch.org/whl/cu121 --force-reinstall

# Verify PyTorch detects CUDA:
uv run python -c "import torch; print('CUDA available:', torch.cuda.is_available())"
```

#### Step 4: Run & Select Local Mode
1. Start the application (`uv run python main.py`).
2. Open Settings (`Ctrl+,` or File -> Settings).
3. Select **Transcription Mode: Local (faster-whisper) - Offline**.
4. Choose a **Local Model Size** suitable for your VRAM:
    *   `tiny` / `base`: < 2GB VRAM (extremely fast)
    *   `small` / `medium`: 2GB - 4GB VRAM (balanced)
    *   `large-v3`: > 6GB VRAM (high accuracy)
5. The service will automatically load on `cuda` if PyTorch reports CUDA is available. If GPU setup is missing, it will safely fall back to CPU execution.
