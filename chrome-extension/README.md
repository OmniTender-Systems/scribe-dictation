# 🎙️ Private Scribe — Chrome OS & Browser Extension (Manifest V3)

100% Offline AI Voice Dictation for Chrome OS, Chromebooks, and all Chromium browsers (Chrome, Edge, Brave).

---

## ⚡ How It Works
1. **Push-to-Talk Hotkey**: Hold `Alt + S` on any webpage (Google Docs, Gmail, Notion, Slack, Obsidian Web, ChatGPT, Canvas).
2. **Offline AI Processing**: Audio is captured via 16kHz Web Audio and transcribed **100% locally on your machine** using ONNX Runtime Web / Transformers.js Whisper models (`whisper-tiny.en`, `whisper-base.en`).
3. **Atomic Auto-Paste**: Releasing the key auto-pastes the transcribed text directly at your cursor into the active input or contenteditable element.
4. **Zero Cloud Uploads**: Works completely offline without internet or server APIs.

---

## 💻 Installing on Chrome OS / Chromebook / Chrome Desktop

### Step 1: Open Extensions Page
1. In Chrome, navigate to `chrome://extensions`.
2. Toggle on **Developer mode** in the top right corner.

### Step 2: Load Unpacked Extension
1. Click **Load unpacked** in the top left.
2. Select the `chrome-extension` folder:
   ```text
   C:\Users\subti\repos\scribe-dictation\chrome-extension
   ```
3. The **Private Scribe** icon will appear in your extension toolbar.

### Step 3: Test Dictation
1. Open any text box (e.g. [Notepad Online](https://www.google.com), Gmail, Google Docs).
2. Focus your cursor in the text field.
3. Hold **`Alt + S`**, speak your message, and release.
4. Watch the floating **VoiceCapsule HUD** transcribe and paste your words instantly.

---

## 📦 Directory Structure

```text
chrome-extension/
├── manifest.json         # Manifest V3 configuration & permissions
├── background.js         # Service worker handling commands & lifecycle
├── offscreen/
│   ├── offscreen.html    # Offscreen worker host
│   └── offscreen.js      # 16kHz audio capture & Transformers.js Whisper pipeline
├── content/
│   ├── content.js        # Floating HUD & universal atomic text insertion
│   └── content.css       # Holographic frosted-acrylic visualizer styling
├── popup/
│   ├── popup.html        # Settings modal & model selector
│   ├── popup.css         # Dark-mode styling
│   └── popup.js          # Local settings persistence
└── icons/                # Extension icon assets (16, 32, 48, 128px)
```

---

## 🛡️ Privacy Architecture
- **Audio Capture**: Stored in a temporary Float32 buffer in browser RAM.
- **Inference**: Executed on-device via WebGPU / WebAssembly.
- **Data Retention**: Zero telemetry, zero external logging, zero cloud network calls.
