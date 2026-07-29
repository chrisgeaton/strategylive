// Offscreen document: captures tab + mic audio and streams to backend via WebSocket.
(() => {
  const SERVER_URL = 'ws://localhost:3003/';
  let sessions = new Map(); // tabId -> session

  function buildWsUrl(channels) {
    const params = new URLSearchParams({ kind: 'audio', sample_rate: '48000', channels: String(channels) });
    return `${SERVER_URL}?${params.toString()}`;
  }

  // Signal readiness as soon as the offscreen page loads
  function signalReady() {
    try { chrome.runtime.sendMessage({ type: 'offscreen-ready' }); } catch {}
  }
  // Signal at multiple points to avoid races
  signalReady();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', signalReady, { once: true });
  }

  async function tryFallbackCapture(session, tabId) {
    console.log('Trying fallback capture methods...');
    
    // Fallback 1: Try getDisplayMedia for tab capture
    try {
      console.log('Fallback 1: Attempting getDisplayMedia for tab audio');
      const displayStream = await navigator.mediaDevices.getDisplayMedia({
        video: false,
        audio: {
          mediaSource: 'tab',
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      
      if (displayStream.getAudioTracks().length > 0) {
        session.tab = displayStream;
        console.log('Successfully captured tab audio via getDisplayMedia');
        chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'tab_audio_acquired_fallback' } });
        return;
      }
    } catch (e) {
      console.log('getDisplayMedia fallback failed:', e);
    }

    // Fallback 2: Try system audio capture
    try {
      console.log('Fallback 2: Attempting system audio capture');
      const systemStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          mandatory: {
            chromeMediaSource: 'system',
            echoCancellation: false,
            autoGainControl: false
          }
        },
        video: false
      });
      
      session.tab = systemStream;
      console.log('Successfully captured system audio');
      chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'system_audio_acquired' } });
      return;
    } catch (e) {
      console.log('System audio fallback failed:', e);
    }

    // Final fallback: Mic-only mode
    console.log('All tab capture methods failed, using mic-only mode');
    chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'mic_only_fallback' } });
  }

  async function startSession(tabId, streamId) {
    if (sessions.has(tabId)) return;
    const session = { tabId, channels: 1, ws: null, ctx: null, merger: null, proc: null, mic: null, tab: null };
    sessions.set(tabId, session);
    chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'starting' } });

    try {

    // Primary approach: Use provided streamId
    if (streamId) {
      try {
        console.log('Attempting tab capture with streamId:', streamId);
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            mandatory: {
              chromeMediaSource: 'tab',
              chromeMediaSourceId: streamId
            }
          },
          video: false
        });
        session.tab = stream;
        console.log('Tab audio stream acquired successfully');
        chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'tab_audio_acquired' } });
      } catch (e) {
        console.log('Primary tab capture failed, trying fallback approaches:', e);
        await tryFallbackCapture(session, tabId);
      }
    } else {
      console.log('No streamId provided, trying fallback approaches');
      await tryFallbackCapture(session, tabId);
    }

    // Try to get mic
    try {
      session.mic = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      session.channels = 2;
    } catch { session.channels = 1; }

    session.ctx = new (self.AudioContext || self.webkitAudioContext)({ sampleRate: 48000 });
    
    // Ensure AudioContext starts
    if (session.ctx.state === 'suspended') {
      session.ctx.resume();
    }
    
    let tabSrc = null;
    let micSrc = null;
    let hasTabAudio = false;
    let hasMicAudio = false;
    
    // Create audio sources from captured streams
    if (session.tab) {
      tabSrc = session.ctx.createMediaStreamSource(session.tab);
      hasTabAudio = true;
      console.log('Tab audio source created');
    }
    
    if (session.mic) {
      micSrc = session.ctx.createMediaStreamSource(session.mic);
      hasMicAudio = true;
      console.log('Microphone audio source created');
    }
    
    if (!hasTabAudio && !hasMicAudio) {
      chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'no_audio_sources' } });
      stopSession(tabId);
      return;
    }
    
    // Create the main audio processing and routing setup
    const mainGain = session.ctx.createGain();
    mainGain.gain.value = 1.0;
    
    // Route 1: Direct playback to speakers (so user can hear the meeting)
    if (hasTabAudio) {
      console.log('Routing tab audio to speakers');
      tabSrc.connect(mainGain);
      mainGain.connect(session.ctx.destination);
    }
    
    // Route 2: Audio processing for transcription
    if (hasTabAudio && hasMicAudio) {
      // Both tab and mic audio - create stereo mix for transcription
      session.channels = 2;
      session.merger = session.ctx.createChannelMerger(2);
      micSrc.connect(session.merger, 0, 0);  // Mic on left
      tabSrc.connect(session.merger, 0, 1);  // Tab on right
      session.proc = session.ctx.createScriptProcessor(1024, 2, 2);
      session.merger.connect(session.proc);
      // CRITICAL: ScriptProcessorNode needs to be connected to destination to trigger callback
      session.proc.connect(session.ctx.destination);
      console.log('Setup stereo processing: mic + tab audio');
    } else if (hasTabAudio) {
      // Tab audio only
      session.channels = 1;
      session.proc = session.ctx.createScriptProcessor(1024, 1, 1);
      tabSrc.connect(session.proc);
      // CRITICAL: ScriptProcessorNode needs to be connected to destination to trigger callback
      session.proc.connect(session.ctx.destination);
      console.log('Setup mono processing: tab audio only');
    } else if (hasMicAudio) {
      // Mic audio only
      session.channels = 1;
      session.proc = session.ctx.createScriptProcessor(1024, 1, 1);
      micSrc.connect(session.proc);
      // CRITICAL: ScriptProcessorNode needs to be connected to destination to trigger callback
      session.proc.connect(session.ctx.destination);
      console.log('Setup mono processing: mic audio only');
    }

    // Open WS from offscreen
    chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'ws_connecting' } });
    const wsUrl = buildWsUrl(session.channels);
    console.log('Offscreen: Connecting to', wsUrl);
    session.ws = new WebSocket(wsUrl);
    session.ws.binaryType = 'arraybuffer';
    let connectTimer = setTimeout(() => {
      try { if (session.ws && session.ws.readyState !== WebSocket.OPEN) { chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'ws_connect_timeout' } }); } } catch {}
    }, 3000);
    session.ws.onopen = () => {
      console.log('Offscreen: WebSocket connected');
      clearTimeout(connectTimer);
      chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'connected' } });
      // Start streaming status only after socket opens
      chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'capturing' } });
    };
    session.ws.onclose = (e) => {
      console.log('Offscreen: WebSocket closed', e.code, e.reason);
      clearTimeout(connectTimer);
      chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'disconnected' } });
    };
    session.ws.onerror = (e) => {
      console.log('Offscreen: WebSocket error', e);
      clearTimeout(connectTimer);
      chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'ws_error', error: String(e) } });
    };
    session.ws.onmessage = (event) => {
      try { const msg = JSON.parse(event.data); chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', ...msg } }); } catch {}
    };

    let audioDebugCount = 0;
    session.proc.onaudioprocess = (ev) => {
      if (!session.ws || session.ws.readyState !== WebSocket.OPEN) return;
      
      // Debug audio levels every 100 chunks
      audioDebugCount++;
      if (audioDebugCount % 100 === 0) {
        if (session.channels === 2) {
          const left = ev.inputBuffer.getChannelData(0);
          const right = ev.inputBuffer.getChannelData(1);
          const leftMax = Math.max(...Array.from(left).map(Math.abs));
          const rightMax = Math.max(...Array.from(right).map(Math.abs));
          console.log(`Audio levels - Left (mic): ${leftMax.toFixed(4)}, Right (tab): ${rightMax.toFixed(4)}`);
          
          // Debug first few samples to see actual values
          console.log(`Sample debug - Left[0-3]: ${left[0].toFixed(6)}, ${left[1].toFixed(6)}, ${left[2].toFixed(6)}, ${left[3].toFixed(6)}`);
        } else {
          const mono = ev.inputBuffer.getChannelData(0);
          const monoMax = Math.max(...Array.from(mono).map(Math.abs));
          console.log(`Audio level - Mono: ${monoMax.toFixed(4)}`);
          console.log(`Sample debug - Mono[0-3]: ${mono[0].toFixed(6)}, ${mono[1].toFixed(6)}, ${mono[2].toFixed(6)}, ${mono[3].toFixed(6)}`);
        }
      }
      
      // Send mono to the server (channels: 1 in config)
      if (session.channels === 2) {
        // Mix stereo to mono
        const left = ev.inputBuffer.getChannelData(0);   // Mic
        const right = ev.inputBuffer.getChannelData(1);  // Tab audio
        const ab = new ArrayBuffer(left.length * 4); const view = new DataView(ab); // 4 bytes per sample for stereo
        // Add detailed debugging of actual values before processing
        if (audioDebugCount % 100 === 1) {
          console.log(`RAW AUDIO DEBUG - Left (mic) first 4 samples: ${left[0]}, ${left[1]}, ${left[2]}, ${left[3]}`);
          console.log(`RAW AUDIO DEBUG - Right (tab) first 4 samples: ${right[0]}, ${right[1]}, ${right[2]}, ${right[3]}`);
        }
        
        for (let i = 0; i < left.length; i++) {
          // Process left channel (microphone)
          let leftSample = left[i];
          leftSample = leftSample * 10; // Amplify by 10x for weak mic signals
          leftSample = Math.max(-1, Math.min(1, leftSample)); // Clamp to [-1, 1]
          
          // Process right channel (tab audio) 
          let rightSample = right[i];
          rightSample = rightSample * 10; // Same amplification for consistency
          rightSample = Math.max(-1, Math.min(1, rightSample)); // Clamp to [-1, 1]
          
          // Debug the conversion for first few samples
          if (i < 4 && audioDebugCount % 100 === 1) {
            const leftInt16 = leftSample < 0 ? leftSample * 0x8000 : leftSample * 0x7FFF;
            console.log(`CONVERSION DEBUG [${i}]: left ${left[i]} -> *10 -> ${leftSample} -> int16: ${Math.round(leftInt16)}`);
          }
          
          // Write stereo samples (left, right)
          view.setInt16(i * 4, leftSample < 0 ? leftSample * 0x8000 : leftSample * 0x7FFF, true);
          view.setInt16(i * 4 + 2, rightSample < 0 ? rightSample * 0x8000 : rightSample * 0x7FFF, true);
        }
        
        // Debug the actual bytes being sent
        if (audioDebugCount % 100 === 1) {
          const bytes = new Uint8Array(ab);
          console.log(`BYTES BEING SENT: ${bytes[0]} ${bytes[1]} ${bytes[2]} ${bytes[3]} ${bytes[4]} ${bytes[5]} ${bytes[6]} ${bytes[7]}`);
        }
        
        session.ws.send(ab);
      } else {
        // Single channel (tab only)
        const mono = ev.inputBuffer.getChannelData(0);
        const ab = new ArrayBuffer(mono.length * 2); const view = new DataView(ab);
        for (let i = 0; i < mono.length; i++) {
          // Much more aggressive amplification for very weak signals
          let s = mono[i] * 100; // Amplify by 100x for very weak signals
          s = Math.max(-1, Math.min(1, s)); // Clamp to [-1, 1]
          view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        }
        session.ws.send(ab);
      }
    };

    // Note: capturing status now sent on ws onopen
    } catch (error) {
      console.error('Error in startSession:', error);
      chrome.runtime.sendMessage({
        type: 'assistant-event',
        tabId,
        payload: {
          source: 'sl-assistant',
          owner: 'offscreen',
          type: 'status',
          status: 'error',
          error: `Failed to start session: ${error.message}`
        }
      });
      // Clean up session on error
      stopSession(tabId);
    }
  }

  function stopSession(tabId) {
    const s = sessions.get(tabId); if (!s) return;
    try { s.proc && s.proc.disconnect(); } catch {}
    try { s.merger && s.merger.disconnect(); } catch {}
    try { s.ctx && s.ctx.close(); } catch {}
    try { s.tab && s.tab.getTracks().forEach(t => t.stop()); } catch {}
    try { s.mic && s.mic.getTracks().forEach(t => t.stop()); } catch {}
    try { s.ws && s.ws.close(); } catch {}
    sessions.delete(tabId);
    chrome.runtime.sendMessage({ type: 'assistant-event', tabId, payload: { source: 'sl-assistant', owner: 'offscreen', type: 'status', status: 'stopped' } });
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === 'offscreen-start' && typeof msg.tabId === 'number') startSession(msg.tabId, msg.streamId);
    if (msg?.type === 'offscreen-stop' && typeof msg.tabId === 'number') stopSession(msg.tabId);
    if (msg?.type === 'call-config') {
      // Send call configuration to active sessions
      for (const [tabId, session] of sessions) {
        if (session.ws && session.ws.readyState === WebSocket.OPEN) {
          const configMessage = JSON.stringify({
            type: 'call_config',
            config: msg.config
          });
          session.ws.send(configMessage);
        }
      }
    }
  });
})();
