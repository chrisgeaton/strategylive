import React from 'react'
import { createRoot } from 'react-dom/client'

// Inject CSS for better scrollbar styling
const scrollbarCSS = `
  .custom-scrollbar::-webkit-scrollbar {
    width: 4px;
    height: 4px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 2px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.3);
  }
  .custom-scrollbar {
    scrollbar-width: thin;
    scrollbar-color: rgba(255,255,255,0.2) transparent;
  }
`;

// Inject the CSS into the document
if (typeof document !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = scrollbarCSS;
  document.head.appendChild(style);
}

// Helper functions for speaker display
function getSpeakerColor(speaker?: string): string {
  switch (speaker) {
    case 'sales_rep': return '#2a4a8a'
    case 'prospect': return '#8a4a2a'
    default: return '#4a4a4a'
  }
}

function getSpeakerLabel(speaker?: string): string {
  switch (speaker) {
    case 'sales_rep': return 'You'
    case 'prospect': return 'Prospect'
    default: return 'Unknown'
  }
}

interface TranscriptItem {
  text: string
  speaker?: string
  timestamp?: number
  confidence?: number
  isComplete?: boolean
}

interface ConversationIntelligence {
  segment?: {
    text: string
    speaker: string
    timestamp: number
    confidence: number
    is_complete: boolean
  }
  conversation_state?: {
    phase: string
    recent_segments_count: number
    time_since_prospect_spoke: number | null
  }
  suggestion_ready?: boolean
}

interface Suggestion {
  id: string
  technique: string
  priority: 'high' | 'medium' | 'low'
  text: string
  rationale: string
}

interface SuggestionsMessage {
  type: 'suggestions'
  timestamp: number
  conversation_context: {
    phase: string
    last_speaker: string
    key_topics: string[]
  }
  suggestions: Suggestion[]
}

interface CallConfiguration {
  goal: 'Discovery_Initial' | 'Discovery_Deep' | 'Discovery_Qualification' | 'Demo_Technical' | 'Demo_Executive' | 'Close_Proposal' | 'Close_Negotiation' | 'Follow_up_Proposal' | 'Follow_up_Objections'
  keyQuestion: string
  context: string
  competitors: string[]
  authorityLevel: 'Decision Maker' | 'Influencer' | 'User' | 'Unknown'
}

function App() {
  const [status, setStatus] = React.useState('idle')
  const [owner, setOwner] = React.useState<string>('unknown')
  const [lastError, setLastError] = React.useState<string | null>(null)
  const [transcript, setTranscript] = React.useState<TranscriptItem[]>([])
  const [suggestions, setSuggestions] = React.useState<Suggestion[]>([])
  const [conversationPhase, setConversationPhase] = React.useState<string>('unknown')
  const [suggestionReady, setSuggestionReady] = React.useState<boolean>(false)
  const [suggestionInteractions, setSuggestionInteractions] = React.useState<Record<string, {used?: boolean, helpful?: boolean, dismissed?: boolean}>>({})
  const [conversationContext, setConversationContext] = React.useState<{phase: string, last_speaker: string, key_topics: string[]}>({phase: 'unknown', last_speaker: 'unknown', key_topics: []})
  const [isMinimized, setIsMinimized] = React.useState<boolean>(false)
  const [isCompact, setIsCompact] = React.useState<boolean>(false)
  const [showTranscript, setShowTranscript] = React.useState<boolean>(false)
  const [showSetup, setShowSetup] = React.useState<boolean>(true)
  const [callConfig, setCallConfig] = React.useState<CallConfiguration>({
    goal: 'Discovery_Initial',
    keyQuestion: '',
    context: '',
    competitors: [],
    authorityLevel: 'Unknown'
  })

  // Check if we're in compact mode based on window size
  React.useEffect(() => {
    const checkCompactMode = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      setIsCompact(width < 420 || height < 280);
    };

    checkCompactMode();
    window.addEventListener('resize', checkCompactMode);
    return () => window.removeEventListener('resize', checkCompactMode);
  }, [])

  React.useEffect(() => {
    const onMsg = (ev: MessageEvent) => {
      const data = ev.data || {}
      if (data?.source !== 'sl-assistant') return
      if (data.owner) setOwner(String(data.owner))
      if (data.type === 'status') {
        setStatus(data.status)
        if (data.error) setLastError(String(data.error))
        else if (data.status === 'error') setLastError('Unknown error')
      }
      if (data.type === 'transcript') {
        const intel: ConversationIntelligence = data.conversation_intelligence || {}

        // Create enhanced transcript item
        const transcriptItem: TranscriptItem = {
          text: data.text,
          speaker: intel.segment?.speaker,
          timestamp: intel.segment?.timestamp || Date.now(),
          confidence: intel.segment?.confidence,
          isComplete: intel.segment?.is_complete
        }

        setTranscript((prev) => [...prev.slice(-10), transcriptItem])

        // Update conversation intelligence state
        if (intel.conversation_state?.phase) {
          setConversationPhase(intel.conversation_state.phase)
        }
        if (typeof intel.suggestion_ready === 'boolean') {
          setSuggestionReady(intel.suggestion_ready)
        }
      }
      if (data.type === 'suggestion') setSuggestions((prev) => [{
        id: `legacy_${Date.now()}`,
        technique: 'general_coaching',
        priority: 'medium' as const,
        text: data.suggestion,
        rationale: 'AI-generated coaching suggestion'
      }, ...prev].slice(0, 5))
      if (data.type === 'suggestions') {
        const suggestionsData: SuggestionsMessage = data
        setSuggestions(suggestionsData.suggestions)
        setConversationContext(suggestionsData.conversation_context)
      }
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  // Suggestion interaction handlers
  const handleSuggestionUse = (suggestionId: string) => {
    setSuggestionInteractions(prev => ({
      ...prev,
      [suggestionId]: { ...prev[suggestionId], used: true }
    }))
    // TODO: Send feedback to backend
  }

  const handleSuggestionFeedback = (suggestionId: string, helpful: boolean) => {
    setSuggestionInteractions(prev => ({
      ...prev,
      [suggestionId]: { ...prev[suggestionId], helpful }
    }))
    // TODO: Send feedback to backend
  }

  const handleSuggestionDismiss = (suggestionId: string) => {
    setSuggestionInteractions(prev => ({
      ...prev,
      [suggestionId]: { ...prev[suggestionId], dismissed: true }
    }))
  }

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return '#e74c3c'
      case 'medium': return '#f39c12'
      case 'low': return '#95a5a6'
      default: return '#95a5a6'
    }
  }

  const getPriorityIcon = (priority: string) => {
    switch (priority) {
      case 'high': return '🔥'
      case 'medium': return '💡'
      case 'low': return '💭'
      default: return '💡'
    }
  }

  return (
    <div className="custom-scrollbar" style={{
      padding: isCompact ? 8 : 12,
      background: 'rgba(15,15,20,0.75)',
      color: '#fff',
      height: '100%',
      boxSizing: 'border-box',
      borderRadius: 16,
      backdropFilter: 'blur(12px)',
      fontSize: isCompact ? '14px' : '16px',
      border: '1px solid rgba(255,255,255,0.1)'
    }}>
      <div style={{
        fontWeight: 600,
        marginBottom: isMinimized ? 0 : (isCompact ? 6 : 8),
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: isCompact ? '13px' : '14px'
      }}>
        <span>{isCompact ? 'SL Assistant' : 'StrategyLive Assistant'}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: isCompact ? 4 : 8 }}>
          {!isMinimized && (
            <>
              <span style={{ fontSize: 11, opacity: 0.7 }}>{status}</span>
              <button
                onClick={() => setShowTranscript(!showTranscript)}
                style={{
                  background: 'rgba(60, 60, 70, 0.6)',
                  border: '1px solid rgba(255,255,255,0.2)',
                  color: '#fff',
                  fontSize: 11,
                  padding: '3px 6px',
                  borderRadius: 4,
                  cursor: 'pointer',
                  opacity: 0.8
                }}
                title={showTranscript ? 'Hide transcript' : 'Show transcript'}
              >
                📝
              </button>
              <ControlButtons status={status} />
            </>
          )}
          <button
            onClick={() => {
              const newMinimized = !isMinimized;
              setIsMinimized(newMinimized);
              // Send message to parent to resize iframe
              try {
                window.parent.postMessage({
                  source: 'sl-overlay',
                  type: newMinimized ? 'minimize' : 'expand'
                }, '*')
              } catch {}
            }}
            style={{
              background: 'rgba(60, 60, 70, 0.6)',
              border: '1px solid rgba(255,255,255,0.2)',
              color: '#fff',
              fontSize: 12,
              padding: '4px 8px',
              borderRadius: 6,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4
            }}
            title={isMinimized ? 'Expand overlay' : 'Minimize overlay'}
          >
            {isMinimized ? '📈' : '📉'}
          </button>
        </div>
      </div>
      {!isMinimized && showSetup && (
        <div style={{
          background: 'rgba(25, 45, 65, 0.6)',
          padding: isCompact ? 8 : 12,
          borderRadius: 8,
          marginBottom: 8,
          border: '1px solid rgba(100, 150, 200, 0.3)'
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: '#A0C8F0' }}>
            📋 Pre-Call Setup (30 seconds)
          </div>

          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 11, opacity: 0.9, display: 'block', marginBottom: 3 }}>Call Goal:</label>
            <select
              value={callConfig.goal}
              onChange={(e) => setCallConfig(prev => ({ ...prev, goal: e.target.value as CallConfiguration['goal'] }))}
              style={{
                width: '100%',
                padding: '4px 6px',
                fontSize: 12,
                background: 'rgba(40, 40, 50, 0.8)',
                border: '1px solid rgba(255,255,255,0.2)',
                borderRadius: 4,
                color: '#fff'
              }}
            >
              <optgroup label="Discovery Calls">
                <option value="Discovery_Initial">Initial Discovery - Building rapport & understanding needs</option>
                <option value="Discovery_Deep">Deep Discovery - Uncovering pain points & implications</option>
                <option value="Discovery_Qualification">Qualification - Authority, budget, timeline, process</option>
              </optgroup>
              <optgroup label="Demo Calls">
                <option value="Demo_Technical">Technical Demo - Feature focused for users</option>
                <option value="Demo_Executive">Executive Demo - ROI & strategic value focused</option>
              </optgroup>
              <optgroup label="Closing Calls">
                <option value="Close_Proposal">Proposal Presentation - Walking through solution</option>
                <option value="Close_Negotiation">Negotiation - Price, terms, contract discussion</option>
              </optgroup>
              <optgroup label="Follow-up Calls">
                <option value="Follow_up_Proposal">Following up on proposal - Status & next steps</option>
                <option value="Follow_up_Objections">Objection handling - Addressing concerns raised</option>
              </optgroup>
            </select>
          </div>

          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 11, opacity: 0.9, display: 'block', marginBottom: 3 }}>Key Question (What's the #1 thing you must ask?):</label>
            <input
              type="text"
              value={callConfig.keyQuestion}
              onChange={(e) => setCallConfig(prev => ({ ...prev, keyQuestion: e.target.value }))}
              placeholder="e.g., What's your biggest challenge with...?"
              style={{
                width: '100%',
                padding: '4px 6px',
                fontSize: 12,
                background: 'rgba(40, 40, 50, 0.8)',
                border: '1px solid rgba(255,255,255,0.2)',
                borderRadius: 4,
                color: '#fff',
                boxSizing: 'border-box'
              }}
            />
          </div>

          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 11, opacity: 0.9, display: 'block', marginBottom: 3 }}>Context (Anything important about this prospect?):</label>
            <textarea
              value={callConfig.context}
              onChange={(e) => setCallConfig(prev => ({ ...prev, context: e.target.value }))}
              placeholder="e.g., 50-person startup, uses Salesforce, mentioned budget concerns..."
              style={{
                width: '100%',
                padding: '4px 6px',
                fontSize: 12,
                background: 'rgba(40, 40, 50, 0.8)',
                border: '1px solid rgba(255,255,255,0.2)',
                borderRadius: 4,
                color: '#fff',
                minHeight: '40px',
                resize: 'vertical',
                boxSizing: 'border-box'
              }}
            />
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={() => {
                setShowSetup(false);
                // Send config to backend
                try {
                  window.parent.postMessage({
                    source: 'sl-overlay',
                    type: 'call_config',
                    config: callConfig
                  }, '*');
                } catch {}
              }}
              style={{
                background: 'linear-gradient(135deg, #4A90E2, #357ABD)',
                border: 'none',
                color: '#fff',
                fontSize: 12,
                padding: '6px 12px',
                borderRadius: 6,
                cursor: 'pointer',
                fontWeight: 600
              }}
            >
              Start Call Coaching
            </button>
            <div style={{ fontSize: 10, opacity: 0.7 }}>
              {callConfig.keyQuestion ? '✅' : '❌'} Key question set
            </div>
          </div>
        </div>
      )}

      {!isMinimized && !showSetup && (
        <>
          {/* Conversation Intelligence Status Bar */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, fontSize: 11 }}>
            <div style={{
              background: conversationPhase === 'unknown' ? '#333' : '#2a4a2a',
              padding: '4px 8px',
              borderRadius: 4,
              border: '1px solid #444'
            }}>
              Phase: <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{conversationPhase}</span>
            </div>
            <div style={{
              background: suggestionReady ? '#2a4a2a' : '#4a2a2a',
              padding: '4px 8px',
              borderRadius: 4,
              border: '1px solid #444'
            }}>
              AI: <span style={{ fontWeight: 600 }}>{suggestionReady ? 'Ready' : 'Waiting'}</span>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 8 }}>
            {showTranscript && (
              <section style={{
                background: 'rgba(31, 31, 37, 0.6)',
                padding: isCompact ? 8 : 10,
                borderRadius: 8,
                maxHeight: isCompact ? 80 : 120,
                overflow: 'hidden'
              }}>
                <div style={{ fontSize: 12, opacity: 0.9, marginBottom: 4 }}>Live Transcript</div>
                <div className="custom-scrollbar" style={{
                  fontSize: 12,
                  lineHeight: 1.4,
                  maxHeight: '90px',
                  overflowY: 'auto',
                  paddingRight: '8px'
                }}>
                  {transcript.slice(-5).map((item, i, arr) => {
                    const prevItem = i > 0 ? arr[i - 1] : null
                    const showSpeaker = !prevItem || prevItem.speaker !== item.speaker

                    return (
                      <div key={i} style={{ marginBottom: 4, opacity: 0.9 }}>
                        {showSpeaker && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                            <span style={{
                              fontSize: 10,
                              background: getSpeakerColor(item.speaker),
                              padding: '2px 6px',
                              borderRadius: 3,
                              fontWeight: 600,
                              textTransform: 'uppercase'
                            }}>
                              {getSpeakerLabel(item.speaker)}
                            </span>
                            {item.confidence && (
                              <span style={{ fontSize: 10, opacity: 0.6 }}>
                                {Math.round(item.confidence * 100)}%
                              </span>
                            )}
                          </div>
                        )}
                        <div style={{
                          paddingLeft: showSpeaker ? 8 : 16,
                          marginTop: showSpeaker ? 0 : -2
                        }}>
                          {item.text}
                          {item.isComplete && (
                            <span style={{ fontSize: 10, color: '#4a8a4a', marginLeft: 4 }}>✓</span>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>
            )}
        <StatusHelp status={status} lastError={lastError} />
        <section className="custom-scrollbar" style={{
          background: 'rgba(31, 31, 37, 0.5)',
          padding: isCompact ? 8 : 12,
          borderRadius: 8,
          flex: 1,
          overflow: 'auto'
        }}>
          <div style={{ fontSize: 12, opacity: 0.9, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>AI Coaching Suggestions</span>
            {suggestions.length > 0 && (
              <span style={{ fontSize: 10, background: '#2a4a2a', padding: '1px 6px', borderRadius: 3 }}>
                {suggestions.filter(s => s.priority === 'high').length} high priority
              </span>
            )}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: isCompact ? 10 : 12 }}>
            {suggestions.filter(s => !suggestionInteractions[s.id]?.dismissed).slice(0, 2).map((suggestion) => {
              const interaction = suggestionInteractions[suggestion.id] || {}
              const priorityColor = getPriorityColor(suggestion.priority)

              return (
                <div key={suggestion.id} style={{
                  background: 'rgba(25, 25, 35, 0.4)',
                  backdropFilter: 'blur(8px)',
                  border: `2px solid rgba(255, 255, 255, 0.1)`,
                  borderLeft: `4px solid ${priorityColor}`,
                  padding: isCompact ? 12 : 16,
                  borderRadius: isCompact ? 8 : 12,
                  fontSize: isCompact ? 15 : 18,
                  lineHeight: 1.4,
                  cursor: 'pointer',
                  transition: 'all 0.3s ease',
                  opacity: interaction.used ? 0.5 : 0.9,
                  boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
                  transform: 'scale(1)',
                  willChange: 'transform, opacity'
                }}
                onClick={() => handleSuggestionUse(suggestion.id)}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(35, 35, 45, 0.5)'
                  e.currentTarget.style.transform = 'scale(1.02)'
                  e.currentTarget.style.opacity = interaction.used ? '0.6' : '1'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(25, 25, 35, 0.4)'
                  e.currentTarget.style.transform = 'scale(1)'
                  e.currentTarget.style.opacity = interaction.used ? '0.5' : '0.9'
                }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{
                        fontSize: isCompact ? 18 : 20,
                        color: priorityColor,
                        filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.5))'
                      }}>
                        {suggestion.priority === 'high' ? '🎯' : suggestion.priority === 'medium' ? '💡' : '💭'}
                      </span>
                      <span style={{
                        fontSize: isCompact ? 11 : 12,
                        color: priorityColor,
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.8px',
                        textShadow: '0 1px 2px rgba(0,0,0,0.5)'
                      }}>
                        {suggestion.priority}
                      </span>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleSuggestionDismiss(suggestion.id)
                      }}
                      style={{
                        background: 'rgba(255, 255, 255, 0.1)',
                        border: '1px solid rgba(255, 255, 255, 0.2)',
                        color: 'rgba(255, 255, 255, 0.7)',
                        cursor: 'pointer',
                        fontSize: 18,
                        padding: '6px 8px',
                        borderRadius: 6,
                        transition: 'all 0.2s ease'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)'
                        e.currentTarget.style.color = 'rgba(255, 255, 255, 1)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'
                        e.currentTarget.style.color = 'rgba(255, 255, 255, 0.7)'
                      }}
                      title="Dismiss"
                    >
                      ×
                    </button>
                  </div>
                  <div style={{
                    fontWeight: 600,
                    color: 'rgba(255, 255, 255, 0.95)',
                    marginBottom: interaction.used ? 8 : 0,
                    textShadow: '0 1px 3px rgba(0,0,0,0.6)',
                    letterSpacing: '0.3px'
                  }}>
                    {suggestion.text}
                  </div>
                  {interaction.used && (
                    <div style={{
                      fontSize: isCompact ? 11 : 12,
                      color: 'rgba(74, 138, 74, 0.9)',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      textShadow: '0 1px 2px rgba(0,0,0,0.5)'
                    }}>
                      <span>✓</span> Used
                    </div>
                  )}
                </div>
              )
            })}
            {suggestions.length === 0 && (
              <div style={{ fontSize: 11, opacity: 0.6, textAlign: 'center', padding: 16 }}>
                No coaching suggestions yet. Start a conversation to receive AI-powered guidance.
              </div>
            )}
          </div>
        </section>
          </div>
        </>
      )}
    </div>
  )
}

function ControlButtons({ status }: { status: string }) {
  const canStop = ['connected','capturing'].includes(status)
  const send = (type: 'stop_capture') => {
    try { window.parent.postMessage({ source: 'sl-overlay', type }, '*') } catch {}
  }
  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
      <div style={{
        fontSize: 12,
        padding: '4px 8px',
        borderRadius: 6,
        border: '1px solid rgba(74, 144, 226, 0.4)',
        background: 'linear-gradient(135deg, rgba(74, 144, 226, 0.1), rgba(53, 122, 189, 0.1))',
        color: '#A0C8F0',
        display: 'flex',
        alignItems: 'center',
        gap: 4
      }}>
        🧩 Click extension in toolbar to start
      </div>
      <button
        onClick={() => send('stop_capture')}
        disabled={!canStop}
        style={{
          fontSize: 12,
          padding: '4px 8px',
          borderRadius: 6,
          border: '1px solid rgba(231, 76, 60, 0.4)',
          background: canStop ? 'linear-gradient(135deg, #e74c3c, #c0392b)' : 'rgba(231, 76, 60, 0.2)',
          color: '#fff',
          cursor: canStop ? 'pointer' : 'default',
          transition: 'all 0.2s ease'
        }}
        title={canStop ? 'Stop capture' : 'Not capturing'}
        onMouseEnter={(e) => {
          if (canStop) {
            e.currentTarget.style.boxShadow = '0 2px 8px rgba(231, 76, 60, 0.4)'
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.boxShadow = 'none'
        }}
      >Stop</button>
    </div>
  )
}

function StatusHelp({ status, lastError }: { status: string, lastError: string | null }) {
  let msg: string | null = null
  if (status === 'need_user_gesture') msg = 'Chrome blocked tab audio capture without a user gesture. Click the extension icon in the toolbar to start capture.'
  if (status === 'unsupported_tab_capture') msg = 'Tab capture API not available in this context. Try the toolbar button.'
  if (status === 'permission_denied') msg = 'Microphone permission denied. Allow mic in the address bar and try again.'
  if (status === 'mic_unavailable') msg = 'Microphone unavailable. Falling back to tab-only audio.'
  if (status === 'error') msg = 'An error occurred during capture. Check the console for details.'
  if (status === 'stream_id_failed') msg = 'Could not negotiate tab audio stream. Try clicking the extension icon/popup Start again to provide a user gesture.'
  if (status === 'use_toolbar_start') msg = 'To avoid screen sharing in Meet, please use the extension toolbar button to start capture.'
  if (status === 'stream_id_required') msg = 'Please open the extension popup (toolbar) and click Start to grant tab audio access.'
  if (status === 'ws_connecting') msg = 'Connecting to backend… Ensure the server is running on port 3003.'
  if (status === 'ws_connect_timeout') msg = 'Backend connection timed out. Is the server running and reachable on ws://localhost:3003/?'
  if (status === 'ws_error') msg = 'Backend connection error. Check the server and firewall settings.'
  if (!msg && lastError) msg = lastError
  if (!msg) return null
  return (
    <div style={{ background: '#3a2a2a', border: '1px solid #6b3b3b', color: '#ffd7d7', padding: 8, borderRadius: 8, fontSize: 12 }}>
      {msg}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
