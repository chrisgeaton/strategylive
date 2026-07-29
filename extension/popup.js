async function getActiveTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.id;
}

document.getElementById('start').addEventListener('click', async () => {
  console.log('Popup: Start button clicked');
  const tabId = await getActiveTabId();
  let streamId = null;
  
  if (chrome.tabCapture && chrome.tabCapture.getMediaStreamId && tabId) {
    try {
      console.log('Popup: Attempting to get streamId for tab', tabId);
      streamId = await new Promise((resolve, reject) => {
        chrome.tabCapture.getMediaStreamId({ 
          targetTabId: tabId 
        }, (id) => {
          if (chrome.runtime.lastError || !id) {
            console.log('Popup: getMediaStreamId failed:', chrome.runtime.lastError || 'No ID returned');
            reject(chrome.runtime.lastError || new Error('getMediaStreamId failed'));
          } else {
            console.log('Popup: Successfully got streamId:', id);
            resolve(id);
          }
        });
      });
    } catch (e) {
      console.warn('Popup: getMediaStreamId failed, background will try alternatives:', e);
      document.getElementById('status').textContent = 'Stream ID failed, trying alternatives...';
    }
  }
  
  if (tabId) {
    console.log('Popup: Sending start message with streamId:', streamId);
    chrome.runtime.sendMessage({ type: 'bg-start-capture', tabId, streamId });
    document.getElementById('status').textContent = streamId ? 'Starting with tab capture…' : 'Starting with fallback methods…';
  } else {
    document.getElementById('status').textContent = 'Error: No active tab found';
  }
});

document.getElementById('stop').addEventListener('click', async () => {
  const tabId = await getActiveTabId();
  if (tabId) chrome.runtime.sendMessage({ type: 'bg-stop-capture', tabId });
  document.getElementById('status').textContent = 'Stopped';
});

document.getElementById('test-health').addEventListener('click', async () => {
  const healthEl = document.getElementById('health-status');
  healthEl.textContent = 'Testing...';
  try {
    await new Promise((resolve, reject) => {
      const ws = new WebSocket('ws://localhost:3003');
      const timer = setTimeout(() => { ws.close(); reject(new Error('timed out')); }, 3000);
      ws.onopen = () => { clearTimeout(timer); ws.close(); resolve(); };
      ws.onerror = () => { clearTimeout(timer); reject(new Error('not reachable')); };
    });
    healthEl.textContent = '✓ Backend reachable on ws://localhost:3003';
  } catch (e) {
    healthEl.textContent = `✗ Backend not reachable (${e.message}). Start it with: python whisper_server.py`;
  }
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.source === 'sl-assistant' && msg.type === 'status') {
    document.getElementById('status').textContent = `Status: ${msg.status}`;
  }
});
