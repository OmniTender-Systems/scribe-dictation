## 2026-08-15 — Version 1.0.0 (Production Release)

### Added
- **Full Offline Local Whisper Engine**: Added offline transcription using `faster-whisper` (tiny, base, small, medium, large-v3) with zero cloud dependencies.
- **Hardware-Locked Pro Licensing**: Machine fingerprint verification with offline cached activation and Gumroad integration.
- **Authentic Retro Tape Recorder Acoustics**: Instant physical mechanical latch/release click audio feedback using zero-latency memory buffers.
- **Curated Global Hotkey Presets**: Configurable hotkeys (`Ctrl + Win`, `Ctrl + Shift`, `Ctrl + Alt`, `Ctrl + Space`, `F1-F12`, `Caps Lock`) that work reliably system-wide.
- **Export Capabilities**: Direct transcription export to `.txt`, `.md` (Markdown), and `.srt` (Subtitles).
- **Sound Effects Toggle**: Option in Settings to toggle acoustic feedback.

### Fixed
- Fixed duplicate transcription paste bug by filtering OS key-repeat events and verifying active window focus.
- Eliminated audio popping by transitioning to high-quality synthesized acoustic models.
- Upgraded paste simulation with atomic debouncing to ensure single-keystroke emission into target applications.
- Synchronized standalone distribution build with taskbar launcher.

---

## 2026-07-15

### Added
- Global hotkey, auto-paste, and system tray (#88cec80, #92589ee)
- Property/fuzz tests for WAV header parsing (#7)

### Fixed
- Resolved pre-existing ruff lint errors blocking CI (#b80fec9)
- CI: added ruff as dev dependency for `uv run ruff check` (#715b9fb)

### Docs
- Added START_HERE.md routing back to neural-network hub (#d8f869b)
- Added multi-agent coordination section with kanban reference (#1938f49)
