// offscreen.js — Offline Audio Processor & Local Whisper AI Pipeline
import { pipeline, env } from "https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2";

// Configure Transformers.js for local/browser IndexedDB caching
env.allowLocalModels = false;
env.useBrowserCache = true;
env.backends.onnx.wasm.numThreads = Math.min(4, navigator.hardwareConcurrency || 2);

let transcriber = null;
let currentModelName = "Xenova/whisper-tiny.en";
let isModelLoading = false;

let audioContext = null;
let mediaStream = null;
let processorNode = null;
let audioChunks = [];
let activeTabId = null;
let recordingStartTime = 0;

// Synthesize retro mechanical tactile click sounds via Web Audio
function playAudioCue(type) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === "start") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.06);
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.06);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.06);
    } else if (type === "stop") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(780, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(360, ctx.currentTime + 0.07);
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.07);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.07);
    }
  } catch (e) {
    // Ignore audio cue errors if context is blocked
  }
}

// Lazy load / preload the local Whisper pipeline
async function getTranscriber(modelName = "Xenova/whisper-tiny.en", progressCallback = null) {
  if (transcriber && currentModelName === modelName) {
    return transcriber;
  }

  isModelLoading = true;
  currentModelName = modelName;

  try {
    transcriber = await pipeline("automatic-speech-recognition", modelName, {
      quantized: true,
      progress_callback: progressCallback,
    });
    isModelLoading = false;
    return transcriber;
  } catch (err) {
    isModelLoading = false;
    console.error("Failed to load local Whisper model:", err);
    throw err;
  }
}

// Start Microphone Capture (16kHz PCM Float32 buffer)
async function startRecording(tabId, settings = {}) {
  activeTabId = tabId;
  audioChunks = [];
  recordingStartTime = performance.now();

  if (settings.audioFeedback !== false) {
    playAudioCue("start");
  }

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(mediaStream);

    // Use ScriptProcessor / AudioWorklet to capture raw 16kHz mono Float32 audio
    processorNode = audioContext.createScriptProcessor(4096, 1, 1);
    processorNode.onaudioprocess = (e) => {
      const channelData = e.inputBuffer.getChannelData(0);
      audioChunks.push(new Float32Array(channelData));
    };

    source.connect(processorNode);
    processorNode.connect(audioContext.destination);

    // Warm up the model in background if not already loaded
    const modelToUse = settings.model || "Xenova/whisper-tiny.en";
    getTranscriber(modelToUse).catch(() => {});
  } catch (err) {
    console.error("Microphone access denied or error:", err);
    chrome.runtime.sendMessage({
      type: "TRANSCRIPTION_ERROR",
      tabId: activeTabId,
      error: "Microphone permission denied. Please allow microphone access in Chrome settings.",
    });
  }
}

// Stop Microphone & Run Offline Whisper Inference
async function stopRecording(tabId) {
  const durationMs = performance.now() - recordingStartTime;

  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }

  if (processorNode && audioContext) {
    processorNode.disconnect();
    await audioContext.close();
    processorNode = null;
    audioContext = null;
  }

  playAudioCue("stop");

  // Check if minimum audio was captured
  if (audioChunks.length === 0 || durationMs < 300) {
    chrome.runtime.sendMessage({
      type: "TRANSCRIPTION_COMPLETE",
      tabId: tabId || activeTabId,
      text: "",
      latencyMs: 0,
    });
    return;
  }

  // Concatenate all 16kHz Float32 audio chunks
  const totalLength = audioChunks.reduce((acc, chunk) => acc + chunk.length, 0);
  const fullAudioBuffer = new Float32Array(totalLength);
  let offset = 0;
  for (const chunk of audioChunks) {
    fullAudioBuffer.set(chunk, offset);
    offset += chunk.length;
  }

  // Clear chunks immediately from RAM
  audioChunks = [];

  try {
    const pipe = await getTranscriber(currentModelName);
    const inferStart = performance.now();

    const output = await pipe(fullAudioBuffer, {
      chunk_length_s: 30,
      stride_length_s: 5,
      language: "english",
      task: "transcribe",
      return_timestamps: false,
    });

    const latencyMs = Math.round(performance.now() - inferStart);
    let transcription = (output.text || "").trim();

    // Clean up typical Whisper artifact repetitions
    transcription = transcription.replace(/\s+/g, " ");

    chrome.runtime.sendMessage({
      type: "TRANSCRIPTION_COMPLETE",
      tabId: tabId || activeTabId,
      text: transcription,
      latencyMs: latencyMs,
    });
  } catch (err) {
    console.error("Whisper inference error:", err);
    chrome.runtime.sendMessage({
      type: "TRANSCRIPTION_ERROR",
      tabId: tabId || activeTabId,
      error: "Transcription error: " + err.message,
    });
  }
}

// Listen for messages from background.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "START_OFFSCREEN_RECORDING") {
    startRecording(message.tabId, message.settings);
    sendResponse({ status: "STARTED" });
  } else if (message.type === "STOP_OFFSCREEN_RECORDING") {
    stopRecording(message.tabId);
    sendResponse({ status: "STOPPED" });
  } else if (message.type === "CHECK_MODEL_CACHE") {
    sendResponse({
      isLoaded: !!transcriber,
      model: currentModelName,
      isLoading: isModelLoading,
    });
  }
  return true;
});
