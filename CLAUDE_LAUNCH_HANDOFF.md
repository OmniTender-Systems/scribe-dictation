# 🤝 Agent Handoff: Private Scribe Commercial Launch & Browser Operations

**Context:** The application **Private Scribe (Scribe Dictation)** has reached a production-ready state (tested, verified, bug-free, offline Whisper AI engine, tactile tape sounds, floating acrylic VoiceCapsule HUD, debounced single-paste).

**Claude's Objective:** Automate and execute the browser-based commercial launch tasks (Gumroad file replacement & description update, Hacker News submission, Reddit post).

---

## 📂 Key Files & Resource Locations

| Resource | Path | Notes |
| :--- | :--- | :--- |
| **Release Zip (for Gumroad)** | `C:\Users\subti\Desktop\PrivateScribe-Windows.zip` | Already created and packaged on the Desktop. |
| **Standalone Binary** | `C:\Users\subti\repos\scribe-dictation\dist\PrivateScribe.exe` | Latest 64-bit production executable. |
| **Installer Script** | `C:\Users\subti\repos\scribe-dictation\installer.iss` | Inno Setup configuration for `.exe` installer. |
| **Active Gumroad Product URL** | `https://gumroad.com/l/eyiexi` | Product ID: `eyiexi`. |
| **Gumroad Edit URL** | `https://app.gumroad.com/products/eyiexi/edit` | Direct edit link for the logged-in user. |
| **Landing Page** | `C:\Users\subti\scribe-dictation\landing\index.html` | Updated with live Gumroad URL and pricing. |

---

## 🎯 Task 1: Update Gumroad Listing (`https://app.gumroad.com/products/eyiexi/edit`)

1. **Navigate** to `https://app.gumroad.com/products/eyiexi/edit`.
2. **Product Name:** Set to `Private Scribe — 100% Offline AI Voice Dictation for Windows`.
3. **Summary / Subtitle:** `Speak Freely. Ultra-fast, private AI voice-to-text with global hotkey and instant auto-paste into any Windows app.`
4. **Description:** Paste the following markdown:

```markdown
### 🔒 Tired of Sending Your Private Voice Notes & Confidential Meetings to the Cloud?

Most AI speech-to-text apps (like Otter, Wispr Flow, or OpenAI Whisper Cloud) upload every single word you speak to remote corporate servers. If you're a doctor, lawyer, developer, therapist, or privacy-conscious professional, **that's a major compliance and confidentiality risk.**

**Private Scribe** gives you state-of-the-art AI dictation that runs **100% locally on your machine**. Zero telemetry. Zero cloud uploads. Zero recurring monthly fees.

---

### ⚡ How It Works in 3 Seconds:
1. **Hold your hotkey** (`Ctrl + Win` or custom preset) anywhere in Windows.
2. **Speak naturally** — dictate emails, code, notes, or essays.
3. **Release the key** — your text instantly pastes directly into your active window (Chrome, Word, VS Code, Slack, Obsidian, Terminal, etc.).

---

### 🌟 Why Private Scribe?

- 🔒 **100% Offline & Private:** Powered by local Whisper models. Works with Wi-Fi completely turned off.
- ⚡ **Zero-Latency Global Hotkey:** Push-to-talk convenience anywhere in your operating system.
- 📋 **Seamless Auto-Paste:** Automatically inserts formatted text right at your cursor without manual copying.
- 🪟 **Holographic VoiceCapsule HUD:** Sleek, translucent acrylic floating visualizer that never steals window focus.
- 🎙️ **Tactile Mechanical Feedback:** Retro audio latch/release sounds so you always know when you're recording.
- 💰 **Pay Once, Own Forever:** Stop paying $15–$25/month on SaaS dictation subscriptions. One license, lifetime access.
- 🌐 **Export Ready:** Save your transcriptions in `.txt`, `.md` (Markdown), or `.srt` (Subtitles).

---

### 💻 System Requirements
- **Operating System:** Windows 10 or Windows 11 (64-bit)
- **RAM:** 4 GB minimum (8 GB recommended)
- **Microphone:** Any standard internal or USB microphone

---

### 🛡️ 30-Day Money-Back Guarantee
If Private Scribe doesn't speed up your daily writing workflow and protect your confidentiality, message us within 30 days for a full refund. No questions asked.
```

5. **Upload Content/Files:**
   - Under the **Content** tab, upload `C:\Users\subti\Desktop\PrivateScribe-Windows.zip`.
   - Remove/archive any older versions.
6. **Pricing & License Keys:**
   - Set base price to **$29**.
   - Under Settings, ensure **"Generate a unique license key per sale"** is toggled ON.
7. **Save & Publish Changes**.

---

## 🎯 Task 2: Post to Hacker News (`Show HN`)

1. **Navigate** to `https://news.ycombinator.com/submit`.
2. **Title:** `Show HN: Private Scribe – 100% offline, privacy-first AI dictation for Windows`
3. **URL:** `https://gumroad.com/l/eyiexi`
4. **Text (if text submission):**
```text
Hey HN,

I built Private Scribe because I wanted a fast, native speech-to-text dictation tool on Windows that didn't upload my voice notes, terminal commands, or private documents to third-party cloud servers.

Features:
- Runs local Whisper models directly on CPU/GPU with zero latency and zero telemetry.
- Global push-to-talk (hold hotkey anywhere -> speak -> release to auto-paste into active window).
- Floating holographic VoiceCapsule HUD with real-time acoustic visualizer.
- One-time purchase, lifetime license (no SaaS subscription).

Would love feedback from the community!

Link: https://gumroad.com/l/eyiexi
```

---

## 🎯 Task 3: Post to Reddit (`r/SideProject` & `r/privacy`)

1. **Navigate** to `https://reddit.com/r/SideProject/submit`.
2. **Title:** `I built an offline, zero-cloud alternative to Wispr Flow & Superwhisper for Windows`
3. **Body:**
```text
Hey everyone,

Most AI speech-to-text tools stream your mic audio to corporate servers. If you're working with client data, legal notes, or medical records, that's a real privacy issue.

I built **Private Scribe**, a lightweight native Windows desktop app:
- Runs local Whisper models directly on CPU/GPU.
- Global push-to-talk (Ctrl+Win or custom preset) that auto-pastes text wherever your cursor is.
- Floating translucent audio visualizer HUD that doesn't steal window focus.
- One-time license, no recurring $15/mo SaaS fees.

Check it out here: https://gumroad.com/l/eyiexi (Use code LAUNCH20 for 20% off this week).
```

---

## ✅ Handoff Checklist
- [x] Product binary compiled, tested, and placed at `C:\Users\subti\Desktop\PrivateScribe-Windows.zip`.
- [x] Gumroad product link verified (`https://gumroad.com/l/eyiexi`).
- [x] Copywriting and promotional posts pre-formatted.
- [ ] Gumroad page updated and new zip uploaded.
- [ ] Show HN post published.
- [ ] Reddit post published.
