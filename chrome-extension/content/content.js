// content.js — Floating HUD & Atomic Text Insertion Engine
let isRecording = false;
let isTranscribing = false;
let lastFocusedElement = null;
let hudElement = null;
let hideTimeout = null;

// Track active focused input/textarea/contenteditable
document.addEventListener("focusin", (e) => {
  if (e.target && (e.target.isContentEditable || e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT")) {
    lastFocusedElement = e.target;
  }
});

// Create and inject the floating VoiceCapsule HUD into the page
function createHUD() {
  if (hudElement) return;

  hudElement = document.createElement("div");
  hudElement.id = "private-scribe-hud";
  hudElement.className = "ps-hidden";
  hudElement.innerHTML = `
    <div class="ps-orb ps-idle" id="ps-orb"></div>
    <div class="ps-waveform" id="ps-waveform">
      <div class="ps-bar"></div>
      <div class="ps-bar"></div>
      <div class="ps-bar"></div>
      <div class="ps-bar"></div>
    </div>
    <span class="ps-status-text" id="ps-status-text">Private Scribe</span>
    <span class="ps-badge">Offline AI</span>
  `;

  // Click on HUD to toggle recording
  hudElement.addEventListener("click", () => {
    toggleRecording();
  });

  document.body.appendChild(hudElement);
}

function updateHUD(state, message) {
  createHUD();
  clearTimeout(hideTimeout);
  hudElement.classList.remove("ps-hidden");

  const orb = document.getElementById("ps-orb");
  const waveform = document.getElementById("ps-waveform");
  const statusText = document.getElementById("ps-status-text");

  if (state === "recording") {
    orb.className = "ps-orb";
    waveform.className = "ps-waveform ps-recording";
    statusText.textContent = message || "Listening...";
  } else if (state === "transcribing") {
    orb.className = "ps-orb ps-transcribing";
    waveform.className = "ps-waveform";
    statusText.textContent = message || "Transcribing locally...";
  } else if (state === "success") {
    orb.className = "ps-orb ps-idle";
    waveform.className = "ps-waveform";
    statusText.textContent = message || "Pasted!";
    hideTimeout = setTimeout(() => {
      hudElement.classList.add("ps-hidden");
    }, 2000);
  } else if (state === "error") {
    orb.className = "ps-orb";
    waveform.className = "ps-waveform";
    statusText.textContent = message || "Error";
    hideTimeout = setTimeout(() => {
      hudElement.classList.add("ps-hidden");
    }, 3500);
  }
}

// Start Voice Recording
function startRecording() {
  if (isRecording || isTranscribing) return;
  isRecording = true;
  updateHUD("recording", "Listening (Hold Alt+S)...");

  chrome.storage.local.get(["settings"], (res) => {
    chrome.runtime.sendMessage({
      type: "START_RECORDING",
      settings: res.settings || {},
    });
  });
}

// Stop Voice Recording & Trigger Whisper
function stopRecording() {
  if (!isRecording) return;
  isRecording = false;
  isTranscribing = true;
  updateHUD("transcribing", "Transcribing locally...");

  chrome.runtime.sendMessage({
    type: "STOP_RECORDING",
  });
}

function toggleRecording() {
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
}

// Universal Atomic Text Insertion into Target Element
function insertTextAtCursor(text) {
  if (!text) return;

  const target = lastFocusedElement || document.activeElement;

  // 1. ContentEditable (Notion, Google Docs, Gmail, Slack, Obsidian Web)
  if (target && target.isContentEditable) {
    target.focus();
    const success = document.execCommand("insertText", false, text + " ");
    if (!success) {
      const selection = window.getSelection();
      if (selection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        range.deleteContents();
        const textNode = document.createTextNode(text + " ");
        range.insertNode(textNode);
        range.setStartAfter(textNode);
        range.setEndAfter(textNode);
        selection.removeAllRanges();
        selection.addRange(range);
      }
    }
    target.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }

  // 2. Standard Input or TextArea
  if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT")) {
    target.focus();
    const start = target.selectionStart || 0;
    const end = target.selectionEnd || 0;
    const currentVal = target.value || "";
    const prefix = currentVal.substring(0, start);
    const suffix = currentVal.substring(end);
    const separator = prefix.length > 0 && !prefix.endsWith(" ") ? " " : "";
    const insertion = separator + text + " ";

    target.value = prefix + insertion + suffix;
    target.selectionStart = target.selectionEnd = start + insertion.length;

    target.dispatchEvent(new Event("input", { bubbles: true }));
    target.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }

  // 3. Fallback: Copy to clipboard and notify
  navigator.clipboard.writeText(text).then(() => {
    updateHUD("success", "Copied to clipboard!");
  }).catch(() => {});
}

// Hotkey Listener (Default: Alt + S for hold-to-talk / push-to-talk)
let altSPressed = false;

window.addEventListener("keydown", (e) => {
  // Push to talk: Alt + S
  if (e.altKey && (e.key === "s" || e.key === "S" || e.code === "KeyS")) {
    if (!altSPressed) {
      altSPressed = true;
      e.preventDefault();
      startRecording();
    }
  }
});

window.addEventListener("keyup", (e) => {
  if (altSPressed && (e.key === "s" || e.key === "S" || e.code === "KeyS" || !e.altKey)) {
    altSPressed = false;
    e.preventDefault();
    stopRecording();
  }
});

// Messages from Background Service Worker
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "TRIGGER_HOTKEY_TOGGLE") {
    toggleRecording();
  } else if (message.type === "PASTE_TRANSCRIPTION") {
    isTranscribing = false;
    if (message.text) {
      insertTextAtCursor(message.text);
      updateHUD("success", `Pasted (${message.latencyMs}ms)`);
    } else {
      updateHUD("success", "No speech detected");
    }
  } else if (message.type === "TRANSCRIPTION_ERROR") {
    isTranscribing = false;
    isRecording = false;
    updateHUD("error", message.error || "Transcription failed");
  }
});

// Initialize HUD on page load
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", createHUD);
} else {
  createHUD();
}
