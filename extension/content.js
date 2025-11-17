(() => {
  let capturing = false;

  function ensureOverlay() {
    const existing = document.getElementById('sl-assistant-overlay');
    if (existing) return existing;
    const iframe = document.createElement('iframe');
    iframe.id = 'sl-assistant-overlay';
    iframe.style.position = 'fixed';
    iframe.style.top = '16px';
    iframe.style.right = '16px';
    // Responsive sizing based on screen size
    const screenWidth = window.innerWidth;
    const screenHeight = window.innerHeight;

    if (screenWidth < 768) {
      // Mobile-like responsive design
      iframe.style.width = Math.min(screenWidth - 32, 360) + 'px';
      iframe.style.height = Math.min(screenHeight * 0.4, 240) + 'px';
    } else if (screenWidth < 1200) {
      // Tablet-like responsive design
      iframe.style.width = '380px';
      iframe.style.height = '280px';
    } else {
      // Desktop design
      iframe.style.width = '420px';
      iframe.style.height = '300px';
    }
    iframe.style.border = '0';
    iframe.style.zIndex = '2147483000';
    iframe.style.pointerEvents = 'auto';
    iframe.style.boxShadow = '0 4px 24px rgba(0,0,0,0.3)';
    iframe.style.borderRadius = '12px';
    iframe.src = chrome.runtime.getURL('overlay/index.html');
    document.documentElement.appendChild(iframe);

    let dragging = false; let startX = 0; let startY = 0; let startLeft = 0; let startTop = 0;
    iframe.addEventListener('mousedown', (e) => {
      dragging = true; startX = e.clientX; startY = e.clientY;
      const rect = iframe.getBoundingClientRect(); startLeft = rect.left; startTop = rect.top; e.preventDefault();
    });
    window.addEventListener('mousemove', (e) => {
      if (!dragging) return; const dx = e.clientX - startX; const dy = e.clientY - startY;
      const left = Math.max(0, Math.min(window.innerWidth - iframe.offsetWidth, startLeft + dx));
      const top = Math.max(0, Math.min(window.innerHeight - iframe.offsetHeight, startTop + dy));
      iframe.style.left = left + 'px'; iframe.style.top = top + 'px'; iframe.style.right = 'auto'; iframe.style.bottom = 'auto';
    });
    window.addEventListener('mouseup', () => { dragging = false; });

    // Handle window resize for responsive design
    const handleResize = () => {
      const screenWidth = window.innerWidth;
      const screenHeight = window.innerHeight;

      if (screenWidth < 768) {
        iframe.style.width = Math.min(screenWidth - 32, 360) + 'px';
        iframe.style.height = Math.min(screenHeight * 0.4, 240) + 'px';
      } else if (screenWidth < 1200) {
        iframe.style.width = '380px';
        iframe.style.height = '280px';
      } else {
        iframe.style.width = '420px';
        iframe.style.height = '300px';
      }

      // Ensure overlay doesn't go off-screen on resize
      const rect = iframe.getBoundingClientRect();
      if (rect.right > window.innerWidth) {
        iframe.style.left = (window.innerWidth - iframe.offsetWidth - 16) + 'px';
        iframe.style.right = 'auto';
      }
      if (rect.bottom > window.innerHeight) {
        iframe.style.top = (window.innerHeight - iframe.offsetHeight - 16) + 'px';
        iframe.style.bottom = 'auto';
      }
    };

    window.addEventListener('resize', handleResize);
    return iframe;
  }

  function postOverlay(message) {
    const iframe = document.getElementById('sl-assistant-overlay');
    if (!iframe || !iframe.contentWindow) return;
    iframe.contentWindow.postMessage({ source: 'sl-assistant', ...message }, '*');
  }

  function reloadOverlay() {
    console.log('🔄 Reloading StrategyLive overlay...');
    const existing = document.getElementById('sl-assistant-overlay');
    if (existing) {
      existing.remove();
    }
    // Wait a moment then recreate
    setTimeout(() => {
      ensureOverlay();
      // Send a fresh status update if we were capturing
      if (capturing) {
        postOverlay({ type: 'status', status: 'capturing' });
      } else {
        postOverlay({ type: 'status', status: 'idle' });
      }
      console.log('✅ StrategyLive overlay reloaded');
    }, 100);
  }

  // Add keyboard shortcut: Ctrl+Shift+R to reload overlay
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'R') {
      e.preventDefault();
      reloadOverlay();
    }
  });

  // Add global function for console access
  window.reloadStrategyLive = reloadOverlay;

  async function startCapture() {
    if (capturing) return; capturing = true;
    ensureOverlay();
    postOverlay({ type: 'status', status: 'starting' });

    // When starting from UI (no user gesture), we send a message to background
    // which will attempt tab capture and fall back to alternatives if needed
    try {
      chrome.runtime.sendMessage({ type: 'bg-start-capture' });
    } catch (e) {
      console.error('Failed to send start capture message:', e);
      capturing = false;
      postOverlay({ type: 'status', status: 'error', error: 'Failed to communicate with extension background' });
    }
  }

  async function stopCapture() {
    capturing = false;
    chrome.runtime.sendMessage({ type: 'bg-stop-capture' });
    postOverlay({ type: 'status', status: 'stopped' });
  }

  window.addEventListener('message', (ev) => {
    const data = ev.data || {};
    if (data.source !== 'sl-overlay') return;
    // Removed start_capture - users should use toolbar button
    if (data.type === 'stop_capture') stopCapture();
    if (data.type === 'minimize') {
      const iframe = document.getElementById('sl-assistant-overlay');
      if (iframe) {
        iframe.style.width = '180px';
        iframe.style.height = '50px';
      }
    }
    if (data.type === 'expand') {
      const iframe = document.getElementById('sl-assistant-overlay');
      if (iframe) {
        const screenWidth = window.innerWidth;
        const screenHeight = window.innerHeight;
        if (screenWidth < 768) {
          iframe.style.width = Math.min(screenWidth - 32, 360) + 'px';
          iframe.style.height = Math.min(screenHeight * 0.4, 240) + 'px';
        } else if (screenWidth < 1200) {
          iframe.style.width = '380px';
          iframe.style.height = '280px';
        } else {
          iframe.style.width = '420px';
          iframe.style.height = '300px';
        }
      }
    }
    if (data.type === 'call_config') {
      // Send call configuration to background script
      chrome.runtime.sendMessage({
        type: 'bg-call-config',
        config: data.config
      });
    }
  });

  function detectFellowOverlay() {
    const iframes = Array.from(document.querySelectorAll('iframe'));
    return iframes.some(f => { try { const src = f.getAttribute('src') || ''; return /\bfellow\.(ai|app|co)\b/.test(src); } catch { return false; } });
  }
  function avoidOverlayConflict() {
    const overlay = document.getElementById('sl-assistant-overlay'); if (!overlay) return;
    if (detectFellowOverlay()) { overlay.style.top = 'auto'; overlay.style.right = 'auto'; overlay.style.left = '16px'; overlay.style.bottom = '16px'; }
  }

  if (location.host.endsWith('meet.google.com')) {
    ensureOverlay(); avoidOverlayConflict();
    const mo = new MutationObserver(() => avoidOverlayConflict()); mo.observe(document.documentElement, { childList: true, subtree: true });
  }

  // Receive events from background/offscreen and forward to overlay
  chrome.runtime.onMessage.addListener((payload) => {
    if (payload && payload.source === 'sl-assistant') { postOverlay(payload); }
  });
})();
