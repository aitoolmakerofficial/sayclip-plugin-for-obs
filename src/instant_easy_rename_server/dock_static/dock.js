const ICONS = {
  "save-moment": `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.05" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3.1l2.55 5.16 5.7.83-4.13 4.02.98 5.68L12 16.1l-5.1 2.69.98-5.68-4.13-4.02 5.7-.83L12 3.1Z" fill="currentColor" opacity=".35"/><path d="M12 3.1l2.55 5.16 5.7.83-4.13 4.02.98 5.68L12 16.1l-5.1 2.69.98-5.68-4.13-4.02 5.7-.83L12 3.1Z"/></svg>`,
  "save-recording": `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.05" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.8" y="5" width="16.4" height="14" rx="2.1"/><path d="M7.2 8h9.6"/><circle cx="8.8" cy="12.3" r="2.25"/><circle cx="15.2" cy="12.3" r="2.25"/><path d="M8.1 18.8h7.8l1.5-3.5H6.6l1.5 3.5Z"/><path d="M8.8 12.3h6.4"/></svg>`,
  discard: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.05" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 7h15"/><path d="M9 4h6l1 3H8l1-3Z"/><path d="M6.5 7l.8 13h9.4l.8-13"/><path d="M10 10.5v6M14 10.5v6"/></svg>`,
  ready: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.15" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.2"/><path d="M8.2 12.25l2.35 2.35 5.25-5.55"/></svg>`,
  speak: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.15" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8.7" y="3.2" width="6.6" height="10.6" rx="3.3"/><path d="M5.4 10.6v.8a6.6 6.6 0 0 0 13.2 0v-.8M12 18v3M8.5 21h7"/><path d="M2.9 10.2v3.6M21.1 10.2v3.6"/></svg>`,
  done: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.15" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6.5 9.8 16.7 4 10.9"/><path d="M18.6 13.1A7 7 0 1 1 16.9 7" opacity=".72"/></svg>`,
  error: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.15" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.45 4.75 2.9 17.7A1.55 1.55 0 0 0 4.25 20h15.5a1.55 1.55 0 0 0 1.35-2.3L13.55 4.75a1.8 1.8 0 0 0-3.1 0Z"/><path d="M12 9.2v4.3M12 16.9h.01"/></svg>`,
  offline: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.15" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7.8 18.5H7A4.5 4.5 0 0 1 6.8 9.5 6.1 6.1 0 0 1 18 8.7a4.8 4.8 0 0 1 2 8.85"/><path d="m4.2 4.2 15.6 15.6"/></svg>`,
  busy: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.15" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="4.2" r="1.25" fill="currentColor" stroke="none"/><circle cx="17.5" cy="6.5" r="1.12" fill="currentColor" stroke="none" opacity=".92"/><circle cx="19.8" cy="12" r="1" fill="currentColor" stroke="none" opacity=".82"/><circle cx="17.5" cy="17.5" r=".88" fill="currentColor" stroke="none" opacity=".72"/><circle cx="12" cy="19.8" r=".78" fill="currentColor" stroke="none" opacity=".62"/><circle cx="6.5" cy="17.5" r=".68" fill="currentColor" stroke="none" opacity=".5"/><circle cx="4.2" cy="12" r=".58" fill="currentColor" stroke="none" opacity=".38"/><circle cx="6.5" cy="6.5" r=".5" fill="currentColor" stroke="none" opacity=".28"/></svg>`
};

const STATUS_META = {
  ready: { label: "READY", icon: "ready", title: "", subtitle: "" },
  recording: { label: "RECORDING", icon: "save-recording", title: "Extended Clip", subtitle: "Do not stop recording in OBS." },
  processing: { label: "PROCESSING", icon: "busy", title: "Extended Clip", subtitle: "Please wait." },
  speak: { label: "SPEAK", icon: "speak", title: "", subtitle: "" },
  done: { label: "DONE", icon: "done", title: "", subtitle: "" },
  error: { label: "ERROR", icon: "error", title: "", subtitle: "" },
  offline: { label: "OFFLINE", icon: "offline", title: "", subtitle: "" },
  busy: { label: "BUSY", icon: "busy", title: "", subtitle: "" }
};

const elements = {
  healthBanner: document.querySelector("#healthBanner"),
  healthTitle: document.querySelector("#healthTitle"),
  healthText: document.querySelector("#healthText"),
  saveMoment: document.querySelector("#saveMoment"),
  saveRecording: document.querySelector("#saveRecording"),
  extendedClip: document.querySelector("#extendedClip"),
  discardRecording: document.querySelector("#discardRecording"),
  discardRecordingLabel: document.querySelector("#discardRecordingLabel"),
  extendedClipLabel: document.querySelector("#extendedClipLabel"),
  extendedClipSubtitle: document.querySelector("#extendedClipSubtitle"),
  statusPanel: document.querySelector("#statusPanel"),
  statusIcon: document.querySelector("#statusIcon"),
  statusChip: document.querySelector("#statusChip"),
  statusTitle: document.querySelector("#statusTitle"),
  statusSubtitle: document.querySelector("#statusSubtitle"),
  voiceBlock: document.querySelector("#voiceBlock"),
  voiceTimer: document.querySelector("#voiceTimer"),
  actionMessage: document.querySelector("#actionMessage"),
  micRow: document.querySelector("#micRow"),
  micChip: document.querySelector("#micChip"),
  micDevice: document.querySelector("#micDevice"),
  micMeterTrack: document.querySelector("#micMeterTrack"),
  micMeter: document.querySelector("#micMeter"),
  micPeak: document.querySelector("#micPeak"),
  meterValue: document.querySelector("#meterValue"),
  jobType: document.querySelector("#jobType"),
  jobGame: document.querySelector("#jobGame"),
  jobTranscript: document.querySelector("#jobTranscript"),
  jobOutput: document.querySelector("#jobOutput"),
  jobError: document.querySelector("#jobError"),
  openFolder: document.querySelector("#openFolder")
};

let bridgeConnected = false;
let messageTimer = 0;
let actionLockUntil = 0;
let localListenStartedAt = 0;
let latestStatus = null;

function mountIcons() {
  document.querySelectorAll("[data-icon]").forEach((node) => {
    const name = node.getAttribute("data-icon");
    node.innerHTML = ICONS[name] || "";
  });
}

function setIcon(node, name) {
  if (node && ICONS[name]) node.innerHTML = ICONS[name];
}

function setChip(node, text, variant) {
  node.textContent = String(text || "").toUpperCase();
  node.className = "chip " + variant;
}

function visualStateForPhase(phase) {
  if (!bridgeConnected) return "offline";
  if (phase === "recording") return "recording";
  if (phase === "processing") return "processing";
  if (phase === "listening") return "speak";
  if (phase === "done") return "done";
  if (phase === "error") return "error";
  if (["command_sent", "waiting_for_obs", "waiting_for_file", "transcribing", "renaming"].includes(phase)) return "busy";
  return "ready";
}

function visualStateForJobStatus(status) {
  if (status === "done") return "done";
  if (status === "listening") return "speak";
  if (status === "error") return "error";
  if (["command_sent", "waiting_for_obs", "waiting_for_file", "transcribing", "renaming", "created"].includes(status)) return "busy";
  return "offline";
}

function shortText(text, limit) {
  const max = limit || 88;
  const value = String(text || "").replace(/\s+/g, " ").trim();
  return value.length > max ? value.slice(0, max - 1).trim() + "..." : value;
}

function applyStatus(visual, options = {}) {
  const meta = STATUS_META[visual] || STATUS_META.ready;
  const title = options.title || meta.title;
  const subtitle = options.subtitle ?? meta.subtitle;

  elements.statusPanel.className = "status-panel status-panel--" + visual;
  setIcon(elements.statusIcon, meta.icon);
  setChip(elements.statusChip, meta.label, visual);
  elements.statusTitle.textContent = title;
  elements.statusSubtitle.textContent = subtitle;
  elements.voiceBlock.hidden = visual !== "speak";
  if (visual === "speak" && !localListenStartedAt) {
    localListenStartedAt = Date.now();
  }
  if (visual !== "speak") {
    localListenStartedAt = 0;
  }

  updateActionAvailability(visual);
}

function updateActionAvailability(visual) {
  const locked = Date.now() < actionLockUntil;
  const baseDisabled = locked || !bridgeConnected;
  const moment = actionAvailability("save_moment");
  const recording = actionAvailability("save_recording");
  const extended = latestStatus && latestStatus.extended_clip || { active: false, stage: "idle" };
  const extendedActionName = extended.active ? "extended_clip_finish" : "extended_clip_start";
  const extendedAction = actionAvailability(extendedActionName);
  const discard = actionAvailability("discard_recording");
  elements.saveMoment.disabled = baseDisabled || !moment.enabled;
  elements.saveRecording.disabled = baseDisabled || !recording.enabled;
  elements.extendedClip.disabled = baseDisabled || !extendedAction.enabled;
  elements.discardRecording.disabled = baseDisabled || !discard.enabled;
  elements.saveMoment.title = moment.reason ? actionReasonText(moment.reason) : "";
  elements.saveRecording.title = recording.reason ? actionReasonText(recording.reason) : "";
  elements.extendedClip.title = extendedAction.reason ? actionReasonText(extendedAction.reason) : "";
  elements.discardRecording.title = discard.reason ? actionReasonText(discard.reason) : "";
  elements.saveRecording.classList.toggle("is-active", Boolean(latestStatus && latestStatus.obs && latestStatus.obs.recording_active));
  elements.extendedClip.classList.toggle("is-active", Boolean(extended.active));
  elements.extendedClipLabel.textContent = extended.stage === "processing" ? "PROCESSING" : extended.active ? "FINISH EXTENDED" : "EXTENDED CLIP";
  elements.extendedClipSubtitle.textContent = extended.stage === "processing" ? "Processing" : extended.active ? "Finish" : "Start";
  const discardConfirming = Boolean(discard.confirmation_armed);
  elements.discardRecording.classList.toggle("is-confirming", discardConfirming);
  elements.discardRecordingLabel.textContent = discardConfirming ? "CONFIRM" : "DISCARD";
}

function actionAvailability(name) {
  const actions = latestStatus && latestStatus.actions;
  const action = actions && actions[name];
  if (!action || typeof action.enabled !== "boolean") {
    return { enabled: false, reason: "unknown_action" };
  }
  return {
    enabled: action.enabled,
    reason: action.reason || null,
    confirmation_armed: Boolean(action.confirmation_armed),
    confirmation_expires_in_ms: Number(action.confirmation_expires_in_ms || 0)
  };
}

function actionReasonText(reason) {
  if (reason === "replay_buffer_inactive") return "Replay buffer is not active.";
  if (reason === "recording_inactive") return "Recording is not active.";
  if (reason === "bridge_disconnected") return "Bridge is not connected.";
  if (reason === "busy") return "Action is busy.";
  if (reason === "obs_state_stale") return "OBS state is not available.";
  if (reason === "recording_already_active") return "A recording is already active.";
  if (reason === "extended_clip_active") return "Extended Clip is active.";
  if (reason === "extended_clip_inactive") return "Extended Clip is not active.";
  if (reason === "operation_busy") return "Another operation is still running.";
  if (reason === "processing_committed") return "Extended Clip is already processing.";
  return "Action is unavailable.";
}

function showHealth(kind, title, text) {
  elements.healthBanner.hidden = false;
  elements.healthBanner.className = "health-banner " + kind;
  elements.healthTitle.textContent = title;
  elements.healthText.textContent = text;
}

function hideHealth() {
  elements.healthBanner.hidden = true;
}

function updateHealth(data) {
  bridgeConnected = false;
  const guard = data.obs && data.obs.microphone_guard;
  if (guard && guard.alarm) {
    bridgeConnected = data.bridge === "connected";
    showHealth("error", "MICROPHONE SILENT", guard.message || "Check your microphone. Recording is still running.");
    return;
  }
  const actionSpecificError = data.phase === "error" && Boolean(data.last_error);
  if (data.backend !== "ok") {
    showHealth("error", "BACKEND ERROR", "Backend reported an error.");
    return;
  }
  if (data.bridge === "error" && !actionSpecificError) {
    showHealth("error", "BRIDGE ERROR", "OBS bridge reported an error.");
    return;
  }
  if (data.bridge !== "connected" && !actionSpecificError) {
    showHealth("warning", "BRIDGE OFFLINE", "Commands cannot reach OBS. Start OBS or reload the bridge script.");
    return;
  }
  const mic = data.mic || {};
  if (mic.available === false) {
    bridgeConnected = true;
    showHealth("error", "MIC ERROR", "Microphone is not available.");
    return;
  }
  bridgeConnected = true;
  hideHealth();
}

function updateJob(job) {
  if (!job) {
    setChip(elements.jobType, "Latest", "offline");
    elements.jobGame.textContent = "";
    elements.jobGame.title = "";
    elements.jobTranscript.textContent = "No recent output";
    elements.jobTranscript.title = "";
    elements.jobOutput.textContent = "";
    elements.jobOutput.title = "";
    elements.jobError.textContent = "";
    elements.jobError.title = "";
    elements.openFolder.hidden = true;
    return;
  }

  const status = String(job.status || "created");
  const originalPath = String(job.original_path || "");
  const finalPath = String(job.final_path || "");
  const selectedPath = finalPath || originalPath;
  const outputFilename = (finalPath || originalPath) ? (finalPath || originalPath).split(/[\\/]/).pop() : "";
  const folder = selectedPath ? selectedPath.replace(/[\\/][^\\/]*$/, "") : "";

  const visual = visualStateForJobStatus(status);
  setChip(elements.jobType, "Latest", visual);
  elements.jobGame.textContent = job.game || folder.split(/[\\/]/).pop() || "";
  elements.jobGame.title = folder;
  elements.jobTranscript.textContent = job.transcript || (status === "listening" ? "..." : outputFilename || "");
  elements.jobTranscript.title = job.transcript || "";
  elements.jobOutput.textContent = job.error ? "" : outputFilename;
  elements.jobOutput.title = finalPath || originalPath;
  elements.jobError.textContent = job.error || "";
  elements.jobError.title = job.error || "";
  elements.openFolder.hidden = !selectedPath;
}

function updateState(data, jobs) {
  latestStatus = data;
  updateHealth(data);

  const job = jobs && jobs.length ? jobs[0] : null;
  const phase = String(data.ui_state || data.phase || "idle");
  const visual = visualStateForPhase(phase);

  let title;
  let subtitle;
  if (visual === "error") {
    title = shortText(data.last_error || (job && job.error) || "Action failed");
    subtitle = "";
  } else if (visual === "done" && job) {
    title = "";
    subtitle = "";
  }

  applyStatus(visual, { title, subtitle });

  const mic = data.mic || {};
  const level = Math.max(0, Math.min(1, Number(mic.level || 0)));
  const maxSeconds = Math.max(1, Number(mic.max_record_seconds || 8));
  const elapsedSeconds = visual === "speak"
    ? Math.max(0, Number(mic.elapsed_seconds || 0) || ((Date.now() - localListenStartedAt) / 1000))
    : 0;
  const progress = Math.max(0, Math.min(1, elapsedSeconds / maxSeconds));
  const remainingSeconds = Math.max(0, Number(mic.remaining_seconds || (maxSeconds - elapsedSeconds)));
  const percent = Math.round(progress * 100);
  elements.micMeter.style.width = percent + "%";
  elements.micMeter.classList.toggle("active", Boolean(mic.active));
  elements.micPeak.style.opacity = String(Math.max(0.16, Math.min(0.86, level * 1.25)));
  elements.micPeak.style.transform = "scaleY(" + String(Math.max(0.2, Math.min(1, 0.22 + level * 1.25))) + ")";
  if (typeof elements.micMeterTrack.style.setProperty === "function") {
    elements.micMeterTrack.style.setProperty("--voice-level", String(level));
  } else {
    elements.micMeterTrack.style["--voice-level"] = String(level);
  }
  elements.meterValue.textContent = visual === "speak" ? Math.ceil(remainingSeconds) + "s" : "";
  elements.meterValue.className = "meter-value " + (remainingSeconds <= 2 ? "hot" : remainingSeconds <= 4 ? "warn" : "");

  elements.micDevice.textContent = mic.device || "default";
  elements.micDevice.title = mic.device || "";
  elements.micChip.className = "mic-state " + (mic.available === false ? "error" : "");
  elements.micChip.textContent = mic.available === false ? "Mic error" : "Mic ready";
  elements.micRow.hidden = true;

  updateJob(job);
}

function offlineState() {
  bridgeConnected = false;
  showHealth("error", "API OFFLINE", "Dock cannot reach backend state endpoint.");
  applyStatus("offline", { title: "", subtitle: "" });
}

function showMessage(text, variant) {
  window.clearTimeout(messageTimer);
  elements.actionMessage.hidden = false;
  elements.actionMessage.textContent = text;
  elements.actionMessage.className = "action-message " + variant;
  messageTimer = window.setTimeout(() => {
    elements.actionMessage.hidden = true;
  }, 1800);
}

async function sendAction(path, button) {
  if (!bridgeConnected) {
    showMessage("Bridge is not connected.", "error");
    return;
  }
  let actionName = "save_moment";
  if (path.includes("/save/recording")) actionName = "save_recording";
  if (path.includes("/extended-clip/start")) actionName = "extended_clip_start";
  if (path.includes("/extended-clip/finish")) actionName = "extended_clip_finish";
  if (path.includes("/discard/recording")) actionName = "discard_recording";
  const availability = actionAvailability(actionName);
  if (!availability.enabled) {
    showMessage(actionReasonText(availability.reason), "error");
    return;
  }
  actionLockUntil = Date.now() + 650;
  button.disabled = true;
  try {
    const response = await fetch(path, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
    showMessage(payload.error || "Command failed", "error");
      return;
    }
    if (actionName === "discard_recording" && payload.confirmation_armed && latestStatus && latestStatus.actions) {
      latestStatus.actions.discard_recording = {
        enabled: true,
        reason: null,
        confirmation_armed: true,
        confirmation_expires_in_ms: Number(payload.confirmation_expires_in_ms || 2000)
      };
      updateActionAvailability("ready");
    }
  } catch (error) {
    showMessage("Command failed", "error");
  } finally {
    window.setTimeout(() => updateActionAvailability("ready"), 650);
  }
}

async function poll() {
  try {
    const responses = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      fetch("/jobs", { cache: "no-store" })
    ]);
    if (!responses[0].ok) throw new Error("HTTP " + responses[0].status);
    const status = await responses[0].json();
    const jobsPayload = responses[1].ok ? await responses[1].json() : { jobs: [] };
    updateState(status, jobsPayload.jobs || []);
  } catch (error) {
    offlineState();
  }
}

elements.saveMoment.addEventListener("click", () => {
  sendAction("/api/save/moment", elements.saveMoment);
});

elements.saveRecording.addEventListener("click", () => {
  sendAction("/api/save/recording", elements.saveRecording);
});

elements.extendedClip.addEventListener("click", () => {
  const extended = latestStatus && latestStatus.extended_clip || { active: false };
  const path = extended.active ? "/api/extended-clip/finish" : "/api/extended-clip/start";
  sendAction(path, elements.extendedClip);
});

elements.discardRecording.addEventListener("click", () => {
  sendAction("/api/discard/recording", elements.discardRecording);
});

elements.openFolder.addEventListener("click", async () => {
  elements.openFolder.disabled = true;
  try {
    await fetch("/api/system/open-folder", { method: "POST" });
  } finally {
    elements.openFolder.disabled = false;
  }
});

mountIcons();
poll();
setInterval(poll, 250);
