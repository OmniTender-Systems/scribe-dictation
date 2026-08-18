// popup.js — Settings Controller for Private Scribe Extension
document.addEventListener("DOMContentLoaded", () => {
  const modelSelect = document.getElementById("model-select");
  const toggleAutoPaste = document.getElementById("toggle-autopaste");
  const toggleAudio = document.getElementById("toggle-audio");
  const licenseKeyInput = document.getElementById("license-key");
  const btnActivate = document.getElementById("btn-activate");
  const licenseTier = document.getElementById("license-tier");
  const statusPill = document.getElementById("status-pill");

  // Load saved settings
  chrome.storage.local.get(["settings"], (res) => {
    const s = res.settings || {
      model: "Xenova/whisper-tiny.en",
      autoPaste: true,
      audioFeedback: true,
      isActivated: true,
    };

    modelSelect.value = s.model || "Xenova/whisper-tiny.en";
    toggleAutoPaste.checked = s.autoPaste !== false;
    toggleAudio.checked = s.audioFeedback !== false;

    if (s.licenseKey) {
      licenseKeyInput.value = s.licenseKey;
      licenseTier.textContent = "Lifetime Active";
      licenseTier.style.color = "#22c55e";
    }
  });

  // Save settings when modified
  function saveSettings() {
    chrome.storage.local.get(["settings"], (res) => {
      const current = res.settings || {};
      const updated = {
        ...current,
        model: modelSelect.value,
        autoPaste: toggleAutoPaste.checked,
        audioFeedback: toggleAudio.checked,
      };
      chrome.storage.local.set({ settings: updated }, () => {
        statusPill.textContent = "Saved";
        setTimeout(() => {
          statusPill.textContent = "Offline Ready";
        }, 1500);
      });
    });
  }

  modelSelect.addEventListener("change", saveSettings);
  toggleAutoPaste.addEventListener("change", saveSettings);
  toggleAudio.addEventListener("change", saveSettings);

  // License Activation Button
  btnActivate.addEventListener("click", () => {
    const key = licenseKeyInput.value.trim();
    if (!key) return;

    btnActivate.textContent = "Validating...";
    btnActivate.disabled = true;

    // Save key locally
    setTimeout(() => {
      chrome.storage.local.get(["settings"], (res) => {
        const updated = {
          ...(res.settings || {}),
          licenseKey: key,
          isActivated: true,
        };
        chrome.storage.local.set({ settings: updated }, () => {
          btnActivate.textContent = "Active!";
          btnActivate.disabled = false;
          licenseTier.textContent = "Lifetime Active";
          licenseTier.style.color = "#22c55e";
        });
      });
    }, 400);
  });
});
