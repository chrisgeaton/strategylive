const state = { activeTabId: null, offscreenReady: false };
let offscreenReadyResolve = null;
let offscreenReadyPromise = null;

async function ensureOffscreen() {
  // If already ready, return fast
  if (state.offscreenReady) return;

  let exists = false;
  try { exists = await chrome.offscreen.hasDocument?.(); } catch (e) { console.warn('offscreen.hasDocument error', e); }
  if (exists) { state.offscreenReady = true; return; }

  // Prepare readiness promise BEFORE creating the document to avoid races
  if (!offscreenReadyPromise) {
    offscreenReadyPromise = new Promise((resolve) => { offscreenReadyResolve = resolve; });
  }

  try {
    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: ['USER_MEDIA'],
      justification: 'Recording from chrome.tabCapture API for meeting transcription.'
    });
  } catch (e) {
    console.error('Failed to create offscreen document', e);
    throw e;
  }

  // If readiness already signaled, resolve immediately
  if (state.offscreenReady && offscreenReadyResolve) {
    offscreenReadyResolve(true); offscreenReadyResolve = null; offscreenReadyPromise = null;
    return;
  }

  await Promise.race([
    offscreenReadyPromise,
    new Promise((_, rej) => setTimeout(() => rej(new Error('offscreen_ready_timeout')), 5000))
  ]);
  state.offscreenReady = true;
}

async function startForTab(tabId, providedStreamId) {
  await ensureOffscreen();
  state.activeTabId = tabId;

  // Use the provided streamId if available (from popup user gesture)
  let streamId = providedStreamId || null;

  // If no streamId provided, try to generate one in background
  if (!streamId && chrome.tabCapture && chrome.tabCapture.getMediaStreamId) {
    try {
      console.log('Background: Attempting to generate streamId for tab', tabId);
      streamId = await new Promise((resolve, reject) => {
        chrome.tabCapture.getMediaStreamId({
          targetTabId: tabId
        }, (id) => {
          if (chrome.runtime.lastError || !id) {
            console.log('Background: getMediaStreamId failed:', chrome.runtime.lastError || 'No ID returned');
            reject(chrome.runtime.lastError || new Error('getMediaStreamId failed'));
          } else {
            console.log('Background: Successfully generated streamId:', id);
            resolve(id);
          }
        });
      });
    } catch (e) {
      console.warn('Background: getMediaStreamId failed, offscreen will use fallback methods:', e);
      // Inform content overlay about the failure for diagnostics
      chrome.tabs.sendMessage(tabId, { source: 'sl-assistant', type: 'status', status: 'stream_id_failed', error: String(e) }).catch(() => {});
    }
  }

  // Always proceed even without streamId - offscreen has robust fallback methods
  console.log('Background: Starting offscreen session with streamId:', streamId || 'null (will use fallbacks)');
  chrome.runtime.sendMessage({ type: 'offscreen-start', tabId, streamId });
}

async function stopForTab(tabId) {
  chrome.runtime.sendMessage({ type: 'offscreen-stop', tabId });
  if (state.activeTabId === tabId) state.activeTabId = null;
}

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.id) return;
  if (state.activeTabId === tab.id) await stopForTab(tab.id);
  else await startForTab(tab.id);
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Forward assistant events from offscreen to content script on the active tab
  if (msg && msg.type === 'assistant-event' && msg.tabId) {
    chrome.tabs.sendMessage(msg.tabId, msg.payload).catch(() => {});
    // Also notify other extension views (e.g., popup) for status updates
    try { chrome.runtime.sendMessage(msg.payload); } catch {}
  }
  if (msg && msg.type === 'offscreen-ready') {
    state.offscreenReady = true;
    if (offscreenReadyResolve) { offscreenReadyResolve(true); offscreenReadyResolve = null; offscreenReadyPromise = null; }
  }
  // Content requests explicit start/stop
  if (msg && msg.type === 'bg-start-capture') {
    const id = msg.tabId || sender?.tab?.id;
    if (id) startForTab(id, msg.streamId);
  }
  if (msg && msg.type === 'bg-stop-capture') {
    const id = msg.tabId || sender?.tab?.id;
    if (id) stopForTab(id);
  }
  if (msg && msg.type === 'bg-call-config') {
    // Forward call configuration to offscreen script
    chrome.runtime.sendMessage({
      type: 'call-config',
      config: msg.config
    }).catch(() => {});
  }
});
