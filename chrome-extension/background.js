// background.js — Private Scribe Background Service Worker
const OFFSCREEN_DOCUMENT_PATH = "offscreen/offscreen.html";

// Ensure offscreen document exists for audio capture & local AI execution
async function ensureOffscreenDocument() {
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
    documentUrls: [chrome.runtime.getURL(OFFSCREEN_DOCUMENT_PATH)],
  });

  if (existingContexts.length > 0) {
    return;
  }

  await chrome.offscreen.createDocument({
    url: OFFSCREEN_DOCUMENT_PATH,
    reasons: ["USER_MEDIA", "WORKERS"],
    justification: "Record microphone input and run local Whisper AI speech-to-text inference without network dependency.",
  });
}

// Handle global browser command (e.g. Alt+Shift+V)
chrome.commands.onCommand.addListener(async (command) => {
  if (command === "toggle-dictation") {
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (activeTab && activeTab.id) {
      chrome.tabs.sendMessage(activeTab.id, { type: "TRIGGER_HOTKEY_TOGGLE" }).catch(() => {
        console.log("Active tab could not receive message (might be chrome:// or restricted page).");
      });
    }
  }
});

// Coordinate messages between Content Scripts, Popup, and Offscreen Document
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      if (message.type === "START_RECORDING") {
        await ensureOffscreenDocument();
        chrome.runtime.sendMessage({
          type: "START_OFFSCREEN_RECORDING",
          tabId: sender.tab?.id,
          settings: message.settings,
        });
        sendResponse({ status: "RECORDING_STARTED" });
      } else if (message.type === "STOP_RECORDING") {
        await ensureOffscreenDocument();
        chrome.runtime.sendMessage({
          type: "STOP_OFFSCREEN_RECORDING",
          tabId: sender.tab?.id,
        });
        sendResponse({ status: "RECORDING_STOPPING" });
      } else if (message.type === "TRANSCRIPTION_COMPLETE") {
        // Forward transcription directly back to the tab that initiated it
        if (message.tabId) {
          chrome.tabs.sendMessage(message.tabId, {
            type: "PASTE_TRANSCRIPTION",
            text: message.text,
            latencyMs: message.latencyMs,
          }).catch((err) => console.warn("Failed to deliver transcription to tab:", err));
        }
        sendResponse({ status: "FORWARDED" });
      } else if (message.type === "TRANSCRIPTION_ERROR") {
        if (message.tabId) {
          chrome.tabs.sendMessage(message.tabId, {
            type: "TRANSCRIPTION_ERROR",
            error: message.error,
          }).catch(() => {});
        }
        sendResponse({ status: "ERROR_REPORTED" });
      } else if (message.type === "GET_MODEL_STATUS") {
        await ensureOffscreenDocument();
        chrome.runtime.sendMessage({ type: "CHECK_MODEL_CACHE" }, (resp) => {
          sendResponse(resp || { isLoaded: false });
        });
        return true;
      }
    } catch (err) {
      console.error("Background error:", err);
      sendResponse({ status: "ERROR", error: err.message });
    }
  })();
  return true; // async response flag
});

// Set default configuration on install
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(["settings"], (res) => {
    if (!res.settings) {
      chrome.storage.local.set({
        settings: {
          model: "Xenova/whisper-tiny.en", // Fast, lightweight (39MB)
          autoPaste: true,
          audioFeedback: true,
          quantized: true,
          executionProvider: "webgpu", // Automatic fallback to wasm
          hotkey: "Alt+S",
          isActivated: true,
        },
      });
    }
  });
});
