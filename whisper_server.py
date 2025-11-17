#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Whisper transcription server
Replaces Deepgram with local processing for ultra-low latency
"""

import asyncio
import websockets
import json
import tempfile
import os
import wave
import struct
import threading
import queue
import time
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import numpy as np
import aiohttp
from datetime import datetime
import uuid
import hashlib

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    safe_print("python-dotenv not installed. Install with: pip install python-dotenv")
    safe_print("Using system environment variables only.")

# Avoid Unicode issues by using safe printing function
def safe_print(*args, **kwargs):
    """Print function that handles Unicode encoding errors gracefully"""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # Convert to safe ASCII representation
        safe_args = []
        for arg in args:
            try:
                safe_args.append(str(arg).encode('ascii', 'replace').decode('ascii'))
            except:
                safe_args.append(repr(arg))
        print(*safe_args, **kwargs)

# Session logging functionality
import logging
from pathlib import Path

class SessionLogger:
    """File-based logger for tracking sessions, transcripts, and coaching decisions"""

    def __init__(self):
        # Create logs directory if it doesn't exist
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(exist_ok=True)

        # Create timestamped session log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.logs_dir / f"coaching_session_{timestamp}.log"

        # Setup logger
        self.logger = logging.getLogger('coaching_session')
        self.logger.setLevel(logging.INFO)

        # Clear any existing handlers
        self.logger.handlers.clear()

        # File handler for detailed logging
        file_handler = logging.FileHandler(self.log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.INFO)

        # Formatter for readable logs
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Track session data
        self.session_id = str(uuid.uuid4())[:8]
        self.session_start = datetime.now()
        self.transcript_count = 0
        self.suggestion_count = 0
        self.blocked_suggestion_count = 0

        # Log session start
        self.log_session_start()

    def log_session_start(self):
        """Log session initialization"""
        self.logger.info("="*80)
        self.logger.info(f"COACHING SESSION STARTED")
        self.logger.info(f"Session ID: {self.session_id}")
        self.logger.info(f"Start Time: {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Log File: {self.log_file}")
        self.logger.info("="*80)

    def log_transcript(self, speaker: str, text: str, confidence: float = None, is_final: bool = False):
        """Log transcript entries"""
        self.transcript_count += 1
        status = "FINAL" if is_final else "INTERIM"
        conf_str = f" (confidence: {confidence:.2f})" if confidence else ""

        self.logger.info(f"TRANSCRIPT [{status}] | {speaker.upper()}: {text}{conf_str}")

    def log_suggestion_check(self, speaker: str, text: str, phase: str, suggestion_ready: bool):
        """Log suggestion readiness check"""
        status = "READY" if suggestion_ready else "NOT_READY"
        self.logger.info(f"SUGGESTION_CHECK [{status}] | Phase: {phase} | Speaker: {speaker} | Text: {text[:100]}...")

    def log_suggestion_blocked(self, reason: str, details: str = ""):
        """Log when suggestions are blocked and why"""
        self.blocked_suggestion_count += 1
        detail_str = f" | {details}" if details else ""
        self.logger.info(f"SUGGESTION_BLOCKED | Reason: {reason}{detail_str}")

    def log_suggestions_generated(self, suggestions: List[Dict], phase: str, context: str = ""):
        """Log when suggestions are successfully generated"""
        self.suggestion_count += len(suggestions)
        self.logger.info("="*60)
        self.logger.info(f"SUGGESTIONS_GENERATED | Phase: {phase} | Count: {len(suggestions)}")

        if context:
            self.logger.info(f"Context: {context[:200]}...")

        for i, suggestion in enumerate(suggestions, 1):
            priority = suggestion.get('priority', 'unknown')
            technique = suggestion.get('technique', 'general')
            text = suggestion.get('text', '')
            self.logger.info(f"  [{i}] {priority.upper()} | {technique} | {text}")

        self.logger.info("="*60)

    def log_phase_change(self, old_phase: str, new_phase: str, reason: str = ""):
        """Log conversation phase changes"""
        reason_str = f" | Reason: {reason}" if reason else ""
        self.logger.info(f"PHASE_CHANGE | {old_phase} → {new_phase}{reason_str}")

    def log_error(self, error_type: str, message: str, details: str = ""):
        """Log errors and issues"""
        detail_str = f" | Details: {details}" if details else ""
        self.logger.error(f"ERROR | {error_type}: {message}{detail_str}")

    def log_session_summary(self):
        """Log session summary before closing"""
        duration = datetime.now() - self.session_start
        self.logger.info("="*80)
        self.logger.info("SESSION SUMMARY")
        self.logger.info(f"Duration: {duration}")
        self.logger.info(f"Transcripts: {self.transcript_count}")
        self.logger.info(f"Suggestions Generated: {self.suggestion_count}")
        self.logger.info(f"Suggestions Blocked: {self.blocked_suggestion_count}")
        self.logger.info(f"Log File: {self.log_file}")
        self.logger.info("="*80)

        # Also print to console for immediate feedback
        safe_print(f"📝 Session logged to: {self.log_file}")
        safe_print(f"📊 Summary: {self.transcript_count} transcripts, {self.suggestion_count} suggestions, {self.blocked_suggestion_count} blocked")

# Global session logger instance
session_logger = None

# Add FFmpeg to PATH for this Python session
ffmpeg_path = r"C:\Users\ceato\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0-full_build\bin"
if ffmpeg_path not in os.environ.get('PATH', ''):
    os.environ['PATH'] = ffmpeg_path + ';' + os.environ.get('PATH', '')
    safe_print(f"Added FFmpeg to PATH for Whisper processing")

# Enhanced Suggestion Data Classes
@dataclass
class Suggestion:
    """Enhanced suggestion with technique tracking and priority"""
    id: str
    technique: str
    priority: str  # "high", "medium", "low"
    text: str
    rationale: str
    phase: str
    timestamp: float

class SuggestionTechnique(Enum):
    """Sales coaching techniques"""
    MIRRORING_EXPANSION = "mirroring_expansion"
    QUANTIFICATION_PROBE = "quantification_probe"
    IMPLICATION_QUESTION = "implication_question"
    NEED_PAYOFF_QUESTION = "need_payoff_question"
    EMPATHY_STATEMENT = "empathy_statement"
    TRIAL_CLOSE = "trial_close"
    OBJECTION_HANDLING = "objection_handling"
    VALUE_REINFORCEMENT = "value_reinforcement"
    NEXT_STEP_PROBE = "next_step_probe"
    PAIN_POINT_EXPANSION = "pain_point_expansion"

class SuggestionPriority(Enum):
    """Suggestion priority levels"""
    HIGH = "high"      # Conversation critical moments
    MEDIUM = "medium"  # Good opportunities
    LOW = "low"        # Nice to have

# Conversation Intelligence Classes
class ConversationPhase(Enum):
    OPENING = "opening"
    DISCOVERY = "discovery"
    DEMO = "demo"
    OBJECTION = "objection"
    CLOSING = "closing"
    UNKNOWN = "unknown"

class SpeakerType(Enum):
    SALES_REP = "sales_rep"
    PROSPECT = "prospect"
    UNKNOWN = "unknown"

@dataclass
class TranscriptSegment:
    text: str
    speaker: SpeakerType
    timestamp: float
    confidence: float
    audio_source: str  # "mic" or "tab"
    duration: float
    is_complete_sentence: bool

@dataclass
class ConversationState:
    phase: ConversationPhase
    recent_segments: List[TranscriptSegment]
    last_prospect_speech_time: Optional[float]
    last_suggestion_time: Optional[float]
    conversation_start_time: float
    topic_keywords: List[str]
    # Talk ratio monitoring
    rep_talk_time: float = 0.0
    prospect_talk_time: float = 0.0
    current_speaker_start_time: Optional[float] = None
    current_speaker: Optional[SpeakerType] = None
    last_talk_ratio_alert: Optional[float] = None
    # Question tracking for SPIN methodology
    situation_questions_count: int = 0
    problem_questions_count: int = 0
    implication_questions_count: int = 0
    need_payoff_questions_count: int = 0
    total_questions_count: int = 0
    recent_questions: List[str] = field(default_factory=list)

class ConversationIntelligence:
    def __init__(self):
        self.state = ConversationState(
            phase=ConversationPhase.OPENING,
            recent_segments=[],
            last_prospect_speech_time=None,
            last_suggestion_time=None,
            conversation_start_time=time.time(),
            topic_keywords=[]
        )
        self.max_history = 10
        self.suggestion_cooldown = 45.0  # seconds - much longer between suggestions
        self.min_silence_for_suggestion = 5.0  # seconds - more pause required

    def analyze_audio_channels(self, left_channel: np.ndarray, right_channel: np.ndarray) -> SpeakerType:
        """Determine primary speaker based on audio channel analysis"""
        left_energy = np.mean(np.abs(left_channel))
        right_energy = np.mean(np.abs(right_channel))

        # Left channel = microphone (sales rep)
        # Right channel = tab audio (prospect)
        if left_energy > right_energy * 1.5:  # Mic significantly louder
            return SpeakerType.SALES_REP
        elif right_energy > left_energy * 1.5:  # Tab significantly louder
            return SpeakerType.PROSPECT
        else:
            return SpeakerType.UNKNOWN

    def is_complete_sentence(self, text: str) -> bool:
        """Check if transcript appears to be a complete sentence"""
        if not text:
            return False
        text = text.strip()
        if len(text) < 10:  # Too short to be meaningful
            return False
        # Ends with sentence-ending punctuation
        if text.endswith(('.', '!', '?')):
            return True
        # Contains multiple words and reasonable length
        return len(text.split()) >= 4 and len(text) >= 20

    def detect_conversation_phase(self, recent_text: str) -> ConversationPhase:
        """Detect conversation phase based on recent transcript content"""
        text_lower = recent_text.lower()

        # Opening phase keywords
        if any(word in text_lower for word in ['hi', 'hello', 'nice to meet', 'thanks for', 'appreciate', 'introduction']):
            return ConversationPhase.OPENING

        # Discovery phase keywords
        if any(word in text_lower for word in ['tell me about', 'what are you', 'how do you', 'current situation', 'challenge', 'problem']):
            return ConversationPhase.DISCOVERY

        # Demo phase keywords
        if any(word in text_lower for word in ['show you', 'demonstrate', 'feature', 'here you can see', 'this allows']):
            return ConversationPhase.DEMO

        # Objection phase keywords
        if any(word in text_lower for word in ['but', 'however', 'concern', 'worried', 'expensive', 'cost', 'budget']):
            return ConversationPhase.OBJECTION

        # Closing phase keywords
        if any(word in text_lower for word in ['next steps', 'move forward', 'when can we', 'contract', 'agreement', 'sign']):
            return ConversationPhase.CLOSING

        return ConversationPhase.UNKNOWN

    def update_talk_ratio(self, speaker: SpeakerType, segment_duration: float) -> Optional[str]:
        """Update talk ratio tracking and return alert message if needed"""
        current_time = time.time()

        # If switching speakers, close previous speaker's time
        if self.state.current_speaker != speaker:
            if self.state.current_speaker and self.state.current_speaker_start_time:
                # Add the time for the previous speaker
                previous_duration = current_time - self.state.current_speaker_start_time
                if self.state.current_speaker == SpeakerType.SALES_REP:
                    self.state.rep_talk_time += previous_duration
                else:
                    self.state.prospect_talk_time += previous_duration

            # Start tracking for new speaker
            self.state.current_speaker = speaker
            self.state.current_speaker_start_time = current_time

        # Calculate current talk ratios
        total_talk_time = self.state.rep_talk_time + self.state.prospect_talk_time
        if total_talk_time < 30:  # Need at least 30 seconds of conversation
            return None

        rep_ratio = self.state.rep_talk_time / total_talk_time

        # Check for talk ratio alert (rep talks >70% for 2+ minutes)
        alert_threshold = 0.70
        min_conversation_time = 120  # 2 minutes
        alert_cooldown = 300  # 5 minutes between alerts

        if (total_talk_time >= min_conversation_time and
            rep_ratio > alert_threshold and
            speaker == SpeakerType.SALES_REP and  # Only alert when rep is currently speaking
            (not self.state.last_talk_ratio_alert or
             current_time - self.state.last_talk_ratio_alert > alert_cooldown)):

            self.state.last_talk_ratio_alert = current_time
            return "Ask a question - get them talking"

        return None

    def should_generate_suggestion(self, force: bool = False) -> bool:
        """Determine if conditions are right for generating a suggestion - conservative by default.
        If force=True (e.g., high-priority trigger detected), bypass pause/phase/dialogue checks
        but still respect cooldown and basic quality filters.
        """
        global session_logger
        current_time = time.time()

        # Check cooldown period - much longer now
        if (self.state.last_suggestion_time and
            current_time - self.state.last_suggestion_time < self.suggestion_cooldown):
            reason = f"cooldown period ({current_time - self.state.last_suggestion_time:.1f}s < {self.suggestion_cooldown}s)"
            safe_print(f"🚫 Suggestion blocked: {reason}")
            if session_logger:
                session_logger.log_suggestion_blocked("COOLDOWN", reason)
            return False

        # Need substantial conversation history before suggesting
        required_history = 4 if force else 6
        if len(self.state.recent_segments) < required_history:
            reason = f"not enough conversation ({len(self.state.recent_segments)} < 6 segments)"
            safe_print(f"🚫 Suggestion blocked: {reason}")
            if session_logger:
                session_logger.log_suggestion_blocked("INSUFFICIENT_HISTORY", reason)
            return False

        # Only generate suggestions after prospect speaks (not sales rep)
        last_segment = self.state.recent_segments[-1]
        if last_segment.speaker != SpeakerType.PROSPECT:
            reason = f"last speaker was {last_segment.speaker.value}, not prospect"
            safe_print(f"🚫 Suggestion blocked: {reason}")
            if session_logger:
                session_logger.log_suggestion_blocked("WRONG_SPEAKER", reason)
            return False

        # Check if prospect spoke recently - longer pause required
        if (self.state.last_prospect_speech_time and
            current_time - self.state.last_prospect_speech_time < self.min_silence_for_suggestion):
            reason = f"prospect spoke too recently ({current_time - self.state.last_prospect_speech_time:.1f}s < {self.min_silence_for_suggestion}s)"
            safe_print(f"🚫 Suggestion blocked: {reason}")
            if session_logger:
                session_logger.log_suggestion_blocked("INSUFFICIENT_PAUSE", reason)
            return False

        # Only suggest in meaningful conversation phases (not unknown/opening)
        if self.state.phase in [ConversationPhase.UNKNOWN, ConversationPhase.OPENING]:
            reason = f"conversation phase too early ({self.state.phase.value})"
            safe_print(f"🚫 Suggestion blocked: {reason}")
            if session_logger:
                session_logger.log_suggestion_blocked("EARLY_PHASE", reason)
            return False

        # Require meaningful prospect statement (not just "yes", "ok", etc.)
        prospect_text = last_segment.text.strip().lower()
        if len(prospect_text) < 10 or prospect_text in ['yes', 'ok', 'sure', 'yeah', 'right', 'okay', 'mm-hmm', 'uh-huh']:
            reason = f"prospect statement too brief/simple: '{prospect_text}'"
            safe_print(f"🚫 Suggestion blocked: {reason}")
            if session_logger:
                session_logger.log_suggestion_blocked("BRIEF_STATEMENT", reason)
            return False

        # Ensure we have dialogue between sales rep and prospect (not monologue)
        recent_speakers = [s.speaker for s in self.state.recent_segments[-4:]]
        if len(set(recent_speakers)) < 2:
            reason = "no back-and-forth dialogue detected"
            safe_print(f"🚫 Suggestion blocked: {reason}")
            if session_logger:
                session_logger.log_suggestion_blocked("NO_DIALOGUE", reason)
            return False

        safe_print(f"✅ Suggestion allowed: all conservative checks passed")
        if session_logger:
            context = last_segment.text[:100] + "..." if len(last_segment.text) > 100 else last_segment.text
            session_logger.log_suggestion_check(last_segment.speaker.value, context, self.state.phase.value, True)
        return True

    def add_transcript_segment(self, text: str, audio_source: str, left_channel: np.ndarray, right_channel: np.ndarray) -> Optional[Dict[str, Any]]:
        """Add new transcript segment and return conversation intelligence data"""
        if not text.strip():
            return None

        current_time = time.time()

        # Determine speaker from audio analysis
        speaker = self.analyze_audio_channels(left_channel, right_channel)

        # Update talk ratio tracking and check for alerts
        talk_ratio_alert = self.update_talk_ratio(speaker, 3.0)  # Using default 3-second duration

        # Track questions for SPIN methodology
        question_tracking_alert = self.track_question(text.strip(), speaker)

        # Detect mirroring opportunities
        mirroring_alert = self.detect_mirroring_opportunities(text.strip(), speaker)

        # Detect objection handling opportunities
        objection_alert = self.detect_objection_handling_opportunities(text.strip(), speaker, self.state.recent_segments)

        # Detect emotional intelligence coaching opportunities
        emotional_intelligence_alert = self.detect_emotional_intelligence_coaching(text.strip(), speaker, self.state.recent_segments)

        # Detect value articulation triggers
        value_articulation_alert = self.detect_value_articulation_triggers(text.strip(), speaker, self.state.recent_segments)

        # Detect closing and advancement coaching opportunities
        closing_advancement_alert = self.detect_closing_advancement_coaching(text.strip(), speaker, self.state.recent_segments)

        # Create transcript segment
        segment = TranscriptSegment(
            text=text.strip(),
            speaker=speaker,
            timestamp=current_time,
            confidence=0.8,  # Default confidence - could be enhanced with Whisper confidence
            audio_source=audio_source,
            duration=3.0,  # Chunk duration
            is_complete_sentence=self.is_complete_sentence(text)
        )

        # Add to recent segments
        self.state.recent_segments.append(segment)
        if len(self.state.recent_segments) > self.max_history:
            self.state.recent_segments.pop(0)

        # Update last prospect speech time
        if speaker == SpeakerType.PROSPECT:
            self.state.last_prospect_speech_time = current_time

        # Update conversation phase
        recent_text = " ".join([s.text for s in self.state.recent_segments[-3:]])
        self.state.phase = self.detect_conversation_phase(recent_text)

        # Check if we should generate suggestions
        # Allow high-priority triggers (objection/closing/mirroring) to bypass pause/phase
        force_trigger = bool(objection_alert or closing_advancement_alert or mirroring_alert)
        suggestion_ready = False
        if force_trigger:
            # Apply high bar to avoid spam
            last_segment = self.state.recent_segments[-1]
            enough_history = len(self.state.recent_segments) >= 4
            is_prospect = (last_segment.speaker == SpeakerType.PROSPECT)
            not_brief = len(last_segment.text.strip()) >= 10
            cooldown_ok = (not self.state.last_suggestion_time) or (current_time - self.state.last_suggestion_time >= self.suggestion_cooldown)
            if enough_history and is_prospect and not_brief and cooldown_ok:
                suggestion_ready = True
                if session_logger:
                    context = last_segment.text[:100] + "..." if len(last_segment.text) > 100 else last_segment.text
                    session_logger.log_suggestion_check(last_segment.speaker.value, context, self.state.phase.value, True)
            else:
                # Fall back to standard conservative checks if forced preconditions fail
                suggestion_ready = self.should_generate_suggestion()
        else:
            suggestion_ready = self.should_generate_suggestion()

        return {
            "segment": {
                "text": segment.text,
                "speaker": segment.speaker.value,
                "timestamp": segment.timestamp,
                "confidence": segment.confidence,
                "is_complete": segment.is_complete_sentence
            },
            "conversation_state": {
                "phase": self.state.phase.value,
                "recent_segments_count": len(self.state.recent_segments),
                "time_since_prospect_spoke": current_time - self.state.last_prospect_speech_time if self.state.last_prospect_speech_time else None
            },
            "suggestion_ready": suggestion_ready,
            "coaching_alert": {
                "type": "closing_advancement",
                "message": closing_advancement_alert,
                "priority": "urgent"
            } if closing_advancement_alert else ({
                "type": "objection_handling",
                "message": objection_alert,
                "priority": "critical"
            } if objection_alert else ({
                "type": "value_articulation",
                "message": value_articulation_alert,
                "priority": "critical"
            } if value_articulation_alert else ({
                "type": "talk_ratio",
                "message": talk_ratio_alert,
                "priority": "high"
            } if talk_ratio_alert else ({
                "type": "emotional_intelligence",
                "message": emotional_intelligence_alert,
                "priority": "high"
            } if emotional_intelligence_alert else ({
                "type": "mirroring",
                "message": mirroring_alert,
                "priority": "high"
            } if mirroring_alert else ({
                "type": "question_tracking",
                "message": question_tracking_alert,
                "priority": "medium"
            } if question_tracking_alert else None)))))),
            "question_stats": {
                "total_questions": self.state.total_questions_count,
                "situation_questions": self.state.situation_questions_count,
                "problem_questions": self.state.problem_questions_count,
                "implication_questions": self.state.implication_questions_count,
                "need_payoff_questions": self.state.need_payoff_questions_count,
                "recent_questions": self.state.recent_questions[-3:]  # Last 3 questions
            }
        }

    def analyze_question_type(self, text: str) -> Optional[str]:
        """Analyze text to identify SPIN question types"""
        if not text.strip().endswith('?'):
            return None  # Not a question

        text_lower = text.lower()

        # Situation Questions - Current state, facts, background
        situation_patterns = [
            'what', 'how many', 'how much', 'when', 'where', 'which', 'who',
            'describe', 'tell me about', 'walk me through', 'current', 'currently'
        ]

        # Problem Questions - Pain points, challenges, difficulties
        problem_patterns = [
            'problem', 'challenge', 'issue', 'difficulty', 'trouble', 'struggle',
            'frustrated', 'concern', 'worry', 'dissatisfied', 'unhappy',
            'bottleneck', 'obstacle', 'barrier', 'gap'
        ]

        # Implication Questions - Consequences, effects, impact
        implication_patterns = [
            'what happens if', 'what would happen', 'impact', 'consequence',
            'effect', 'result', 'affect', 'cost', 'risk', 'delay',
            'what does that mean', 'how does that affect', 'what are the implications'
        ]

        # Need-Payoff Questions - Benefits, value, solutions
        need_payoff_patterns = [
            'how important', 'how valuable', 'worth', 'benefit', 'advantage',
            'help', 'solve', 'improve', 'save', 'increase', 'reduce',
            'would it be useful', 'would it help', 'value', 'roi'
        ]

        # Check patterns in order of specificity
        if any(pattern in text_lower for pattern in need_payoff_patterns):
            return 'need_payoff'
        elif any(pattern in text_lower for pattern in implication_patterns):
            return 'implication'
        elif any(pattern in text_lower for pattern in problem_patterns):
            return 'problem'
        elif any(pattern in text_lower for pattern in situation_patterns):
            return 'situation'

        return 'general'  # Generic question

    def track_question(self, text: str, speaker: SpeakerType) -> Optional[str]:
        """Track questions from sales rep and return coaching suggestion if applicable"""
        if speaker != SpeakerType.SALES_REP:
            return None

        question_type = self.analyze_question_type(text)
        if not question_type:
            return None

        # Update question counts
        if question_type == 'situation':
            self.state.situation_questions_count += 1
        elif question_type == 'problem':
            self.state.problem_questions_count += 1
        elif question_type == 'implication':
            self.state.implication_questions_count += 1
        elif question_type == 'need_payoff':
            self.state.need_payoff_questions_count += 1

        self.state.total_questions_count += 1

        # Track recent questions
        if len(self.state.recent_questions) >= 5:
            self.state.recent_questions.pop(0)
        self.state.recent_questions.append(f"{question_type}: {text}")

        # ENHANCED SPIN COACHING LOGIC - Advanced question flow guidance
        total = self.state.total_questions_count
        if total >= 2:  # Start coaching earlier for better guidance
            situation_ratio = self.state.situation_questions_count / total
            problem_ratio = self.state.problem_questions_count / total
            implication_ratio = self.state.implication_questions_count / total
            need_payoff_ratio = self.state.need_payoff_questions_count / total

            # PHASE 1: SITUATION ANALYSIS - Build understanding first
            if total <= 3:
                if situation_ratio < 0.5:
                    return "SPIN COACHING: Start with situation questions. Ask: 'Can you walk me through your current process?' or 'How are you handling [topic] today?'"
                elif situation_ratio >= 0.7 and total >= 3:
                    return "SPIN COACHING: Good situation understanding. Now probe for problems: 'What challenges are you facing with this process?'"

            # PHASE 2: PROBLEM IDENTIFICATION - Find pain points
            elif total <= 6:
                if problem_ratio < 0.3:
                    return "SPIN COACHING: Need more problem identification. Ask: 'What's frustrating about your current situation?' or 'Where are the bottlenecks?'"
                elif problem_ratio >= 0.4 and self.state.implication_questions_count == 0:
                    return "SPIN COACHING: Great problem discovery! Now explore implications: 'What impact does this have on your team/business?'"

            # PHASE 3: IMPLICATION DEVELOPMENT - Amplify the pain
            elif total <= 10:
                if implication_ratio < 0.2 and problem_ratio >= 0.3:
                    return "SPIN COACHING: Problems identified. Dig into consequences: 'What happens if this problem continues?' or 'How does this affect your goals?'"
                elif implication_ratio >= 0.2 and self.state.need_payoff_questions_count == 0:
                    return "SPIN COACHING: Pain established. Now build value: 'How important would it be to solve this?' or 'What would improvement mean to you?'"

            # PHASE 4: NEED-PAYOFF - Create buying vision
            elif total > 10:
                if need_payoff_ratio < 0.15:
                    return "SPIN COACHING: Time for need-payoff questions. Ask: 'How would fixing this help your business?' or 'What benefits would you see?'"

            # ADVANCED SPIN FLOW ANALYSIS

            # Detect stalled discovery (too many of same type)
            if total >= 6:
                if situation_ratio > 0.6:
                    return "SPIN COACHING: Too many situation questions. Move to problems: 'That's helpful context. What's not working well with this setup?'"
                elif problem_ratio > 0.5 and implication_ratio < 0.1:
                    return "SPIN COACHING: Many problems identified. Explore the cost: 'When this happens, what's the impact on productivity/revenue?'"

            # Perfect SPIN progression detection
            if (total >= 8 and situation_ratio > 0.2 and problem_ratio > 0.3 and
                implication_ratio > 0.1 and need_payoff_ratio > 0.1):
                return "SPIN COACHING: Excellent question flow! You're following SPIN methodology perfectly - keep building on their responses."

            # Missing critical components
            if total >= 5:
                if self.state.situation_questions_count == 0:
                    return "SPIN COACHING: Missing situation questions. Understand their current state first: 'Tell me about your current process.'"
                elif self.state.problem_questions_count == 0:
                    return "SPIN COACHING: No problems identified yet. Probe for pain: 'What challenges do you face with this?'"

        # SPECIFIC QUESTION SUGGESTIONS based on conversation context
        recent_prospect_text = ""
        for segment in self.state.recent_segments[-3:]:
            if segment.speaker == SpeakerType.PROSPECT:
                recent_prospect_text += segment.text.lower() + " "

        if recent_prospect_text:
            # They mentioned specific topics - provide contextual SPIN questions
            if "process" in recent_prospect_text or "workflow" in recent_prospect_text:
                return "SPIN COACHING: They mentioned process/workflow. Ask implication: 'How does this process impact your team's efficiency?'"
            elif "team" in recent_prospect_text or "people" in recent_prospect_text:
                return "SPIN COACHING: Team focus detected. Ask need-payoff: 'How important is it to free up your team's time for higher-value work?'"
            elif "cost" in recent_prospect_text or "budget" in recent_prospect_text:
                return "SPIN COACHING: Cost mentioned. Explore implications: 'What's the total cost of the current situation over 12 months?'"

        return None

    def detect_mirroring_opportunities(self, text: str, speaker: SpeakerType) -> Optional[str]:
        """Enhanced mirroring detection - core coaching tool for building rapport and discovery"""
        if speaker != SpeakerType.PROSPECT:
            return None

        text_lower = text.lower()

        # HIGH-VALUE DISCOVERY MIRRORING OPPORTUNITIES
        # These are the most important for building rapport and getting prospects talking

        # 1. GOALS & ASPIRATIONS - Mirror their desired outcomes
        goal_patterns = {
            'growth': ['grow', 'scale', 'expand', 'increase', 'bigger', 'more customers', 'revenue'],
            'efficiency': ['streamline', 'optimize', 'automate', 'faster', 'save time', 'reduce manual'],
            'cost_savings': ['save money', 'reduce costs', 'budget', 'cheaper', 'affordable', 'cost-effective'],
            'competitive_advantage': ['competitive', 'ahead', 'edge', 'better than', 'outperform', 'differentiate'],
            'innovation': ['innovate', 'modern', 'cutting-edge', 'latest', 'new technology', 'digital transformation']
        }

        # 2. PAIN POINTS & FRUSTRATIONS - Critical for empathy building
        pain_patterns = {
            'time_wasting': ['waste time', 'takes forever', 'slow process', 'manual work', 'tedious'],
            'complexity': ['complicated', 'complex', 'confusing', 'hard to use', 'difficult'],
            'reliability': ['unreliable', 'breaks down', 'inconsistent', 'buggy', 'crashes'],
            'poor_support': ['no support', 'unhelpful', 'slow response', 'bad service'],
            'integration_issues': ["doesn't work with", 'integration', 'disconnect', 'silo', 'separate systems'],
            'resource_constraints': ['limited resources', 'small team', 'understaffed', 'tight budget']
        }

        # 3. EMOTIONAL STATES - Build connection through emotional mirroring
        emotional_patterns = {
            'frustration': ['frustrated', 'annoying', 'irritating', 'bothered', 'fed up', 'sick of'],
            'excitement': ['excited', 'thrilled', 'love', 'amazing', 'fantastic', 'perfect'],
            'concern': ['worried', 'concerned', 'nervous', 'anxious', 'hesitant'],
            'urgency': ['urgent', 'asap', 'deadline', 'pressure', 'need it now', 'running out of time'],
            'skepticism': ['not sure', 'doubtful', 'skeptical', 'burned before', 'cautious']
        }

        # 4. INDUSTRY LANGUAGE - Show you speak their language
        industry_terms = [
            'roi', 'kpi', 'metrics', 'dashboard', 'analytics', 'pipeline', 'funnel',
            'churn', 'retention', 'acquisition', 'conversion', 'throughput', 'capacity',
            'compliance', 'governance', 'audit', 'security', 'scalability', 'architecture'
        ]

        # 5. ROLE-SPECIFIC CONCERNS - Mirror their professional priorities
        role_concerns = {
            'ceo': ['revenue', 'growth', 'market share', 'competitive advantage', 'strategy'],
            'cto': ['scalability', 'architecture', 'security', 'performance', 'integration'],
            'ops': ['efficiency', 'process', 'workflow', 'automation', 'reliability'],
            'sales': ['pipeline', 'conversion', 'quota', 'leads', 'closing']
        }

        # Check for GOALS & ASPIRATIONS (highest priority for discovery)
        for goal_type, patterns in goal_patterns.items():
            if any(pattern in text_lower for pattern in patterns):
                return f"Mirror their {goal_type} goal - 'So {goal_type.replace('_', ' ')} is really important to you...'"

        # Check for PAIN POINTS (second highest priority)
        for pain_type, patterns in pain_patterns.items():
            if any(pattern in text_lower for pattern in patterns):
                return f"Mirror their {pain_type.replace('_', ' ')} pain - acknowledge and dig deeper"

        # Check for EMOTIONAL STATES (critical for rapport)
        for emotion, patterns in emotional_patterns.items():
            if any(pattern in text_lower for pattern in patterns):
                return f"Mirror their {emotion} - 'It sounds like you're {emotion}... tell me more'"

        # Check for INDUSTRY TERMINOLOGY (shows expertise)
        for term in industry_terms:
            if term in text_lower:
                return f"Mirror their language - use '{term}' when you respond"

        # Check for ROLE-SPECIFIC language
        for role, concerns in role_concerns.items():
            if any(concern in text_lower for concern in concerns):
                return f"Mirror their {role} priorities - speak to their specific concerns"

        # GENERAL MIRRORING OPPORTUNITIES
        # Key phrases that always indicate mirroring opportunities
        mirror_triggers = [
            'most important', 'biggest challenge', 'main concern', 'top priority',
            'really need', 'have to have', 'deal breaker', 'non-negotiable',
            'currently using', 'been looking for', 'tried before', 'ideal solution'
        ]

        if any(trigger in text_lower for trigger in mirror_triggers):
            return "Mirror their priorities - repeat back what they just said is most important"

        return None

    def detect_emotional_intelligence_coaching(self, text: str, speaker: SpeakerType, recent_segments: List[TranscriptSegment]) -> Optional[str]:
        """Advanced emotional intelligence coaching - read emotions and provide EQ guidance"""
        if speaker != SpeakerType.PROSPECT:
            return None

        text_lower = text.lower()

        # EMOTIONAL STATE DETECTION AND COACHING

        # 1. EXCITEMENT/ENTHUSIASM - Capitalize on positive energy
        excitement_indicators = [
            'excited', 'love this', 'amazing', 'fantastic', 'perfect', 'exactly what we need',
            'this is great', 'wow', 'incredible', 'brilliant', 'awesome', 'thrilled',
            'can\'t wait', 'looks perfect', 'this solves everything'
        ]

        if any(indicator in text_lower for indicator in excitement_indicators):
            return "EMOTIONAL INTELLIGENCE: High enthusiasm detected! Match their energy and momentum. Ask: 'What specifically excites you most about this?' Then move toward next steps while energy is high."

        # 2. FRUSTRATION/STRESS - Acknowledge and empathize
        frustration_indicators = [
            'frustrated', 'annoying', 'driving me crazy', 'fed up', 'sick of', 'hate',
            'terrible', 'awful', 'nightmare', 'disaster', 'killing me', 'exhausted',
            'overwhelmed', 'stressed', 'burned out', 'can\'t take it anymore'
        ]

        if any(indicator in text_lower for indicator in frustration_indicators):
            return "EMOTIONAL INTELLIGENCE: Frustration detected. Acknowledge their pain: 'That sounds really frustrating.' Then dig deeper: 'Help me understand what's been most challenging about this situation.'"

        # 3. CONCERN/WORRY/ANXIETY - Address fears directly
        concern_indicators = [
            'worried', 'concerned', 'nervous', 'anxious', 'scared', 'afraid',
            'not sure', 'hesitant', 'cautious', 'risky', 'what if', 'concerned about'
        ]

        if any(indicator in text_lower for indicator in concern_indicators):
            return "EMOTIONAL INTELLIGENCE: Concern/anxiety detected. Address fears directly: 'I hear you're concerned about [specific worry]. That's completely understandable. What would help you feel more confident about this?'"

        # 4. SKEPTICISM/DOUBT - Build credibility and trust
        skepticism_indicators = [
            'skeptical', 'doubtful', 'not convinced', 'sounds too good', 'been burned before',
            'heard this before', 'promises', 'everyone says that', 'prove it',
            'how do I know', 'what\'s the catch'
        ]

        if any(indicator in text_lower for indicator in skepticism_indicators):
            return "EMOTIONAL INTELLIGENCE: Skepticism detected. Build trust with specifics: 'I understand your skepticism - that's smart. Let me show you exactly how this works with a concrete example from [similar customer].'"

        # 5. IMPATIENCE/URGENCY - Respect their timeline
        urgency_indicators = [
            'urgent', 'asap', 'need it now', 'can\'t wait', 'deadline', 'running out of time',
            'pressure', 'behind schedule', 'time sensitive', 'immediately'
        ]

        if any(indicator in text_lower for indicator in urgency_indicators):
            return "EMOTIONAL INTELLIGENCE: Urgency detected. Acknowledge their timeline: 'I can hear this is time-sensitive for you. Let's focus on the fastest path to get you what you need. What's your ideal timeline?'"

        # 6. CONFUSION/OVERWHELM - Simplify and clarify
        confusion_indicators = [
            'confused', 'don\'t understand', 'complicated', 'overwhelming', 'too much',
            'lost', 'not following', 'can you explain', 'what do you mean',
            'this is complex', 'hard to follow'
        ]

        if any(indicator in text_lower for indicator in confusion_indicators):
            return "EMOTIONAL INTELLIGENCE: Confusion detected. Slow down and simplify: 'Let me break this down into simpler terms.' Focus on one key concept at a time and check for understanding."

        # 7. DISAPPOINTMENT/RESIGNATION - Re-energize with hope
        disappointment_indicators = [
            'disappointed', 'let down', 'expected more', 'not what I hoped',
            'giving up', 'resigned', 'whatever', 'doesn\'t matter', 'fine',
            'I guess', 'settling for'
        ]

        if any(indicator in text_lower for indicator in disappointment_indicators):
            return "EMOTIONAL INTELLIGENCE: Disappointment detected. Re-energize with empathy: 'It sounds like you're not seeing what you hoped for. What would make this feel like a win for you?'"

        # ADVANCED EMOTIONAL PATTERN ANALYSIS

        # 8. ENERGY SHIFT DETECTION - Compare recent segments
        if len(recent_segments) >= 3:
            recent_prospect_texts = [s.text.lower() for s in recent_segments[-3:] if s.speaker == SpeakerType.PROSPECT]

            # Detect energy drop (short responses, minimal engagement)
            recent_lengths = [len(text.split()) for text in recent_prospect_texts]
            if len(recent_lengths) >= 2 and all(length <= 5 for length in recent_lengths[-2:]):
                return "EMOTIONAL INTELLIGENCE: Energy drop detected (short responses). Re-engage: 'I want to make sure I'm covering what matters most to you. What questions do you have?'"

            # Detect increasing positivity
            positive_words = ['good', 'great', 'like', 'yes', 'right', 'exactly', 'perfect']
            positive_count = sum(1 for text in recent_prospect_texts for word in positive_words if word in text)
            if positive_count >= 3:
                return "EMOTIONAL INTELLIGENCE: Increasing positivity! They're warming up. Keep building on this momentum and ask about their decision process."

        # 9. TONE SHIFT DETECTION - Formal to casual or vice versa
        formal_indicators = ['certainly', 'absolutely', 'appreciate', 'understand', 'regarding', 'however']
        casual_indicators = ['yeah', 'yep', 'cool', 'awesome', 'gotcha', 'for sure', 'totally']

        if any(indicator in text_lower for indicator in formal_indicators) and len(text.split()) > 10:
            return "EMOTIONAL INTELLIGENCE: Formal tone detected. They may be cautious or evaluating. Match their professionalism and provide detailed, structured information."

        if any(indicator in text_lower for indicator in casual_indicators):
            return "EMOTIONAL INTELLIGENCE: Casual tone detected. They're comfortable with you! This is good rapport - you can be more direct about next steps."

        # 10. DECISION-MAKING STRESS INDICATORS
        decision_stress = [
            'big decision', 'lot to consider', 'need to think', 'weighing options',
            'pros and cons', 'difficult choice', 'hard to decide', 'many factors'
        ]

        if any(indicator in text_lower for indicator in decision_stress):
            return "EMOTIONAL INTELLIGENCE: Decision stress detected. Help simplify: 'Let's focus on your top 2-3 priorities. What matters most in making this decision?' Then guide them through each priority."

        return None

    def detect_value_articulation_triggers(self, text: str, speaker: SpeakerType, recent_segments: List[TranscriptSegment]) -> Optional[str]:
        """Advanced value articulation coaching - detect value moments and amplify them"""
        if speaker != SpeakerType.PROSPECT:
            return None

        text_lower = text.lower()

        # VALUE ARTICULATION TRIGGER DETECTION

        # 1. DIRECT VALUE EXPRESSIONS - Prospect states value/benefit
        direct_value_indicators = [
            'that would help', 'that would save', 'would be valuable', 'sounds helpful',
            'could improve', 'would make a difference', 'that\'s useful', 'beneficial',
            'advantage', 'benefit', 'value', 'improvement', 'better', 'easier'
        ]

        if any(indicator in text_lower for indicator in direct_value_indicators):
            return "VALUE TRIGGER: They see value! Quantify it: 'Help me understand the specific impact - how much time/money would that save?' Then multiply it: 'Over 12 months, what would that mean?'"

        # 2. ROI/FINANCIAL IMPACT MENTIONS - Build on money talk
        financial_indicators = [
            'save money', 'reduce costs', 'increase revenue', 'roi', 'return on investment',
            'payback', 'budget', 'expensive', 'cheaper', 'cost effective', 'worth it',
            'price', 'investment', 'financial', 'dollar', '$'
        ]

        if any(indicator in text_lower for indicator in financial_indicators):
            return "VALUE TRIGGER: Financial focus detected! Dig deeper: 'What's the current cost of [their problem]?' Then show clear ROI calculation with specific numbers."

        # 3. TIME SAVINGS EXPRESSIONS - Amplify efficiency gains
        time_value_indicators = [
            'save time', 'faster', 'quicker', 'efficient', 'streamline', 'automate',
            'reduce time', 'speed up', 'eliminate manual', 'don\'t have to', 'automatic'
        ]

        if any(indicator in text_lower for indicator in time_value_indicators):
            return "VALUE TRIGGER: Time savings mentioned! Quantify impact: 'How many hours per week would this save?' Then calculate: 'At $[hourly rate], that's $[X] in productivity gains annually.'"

        # 4. COMPETITIVE ADVANTAGE LANGUAGE - Build strategic value
        competitive_indicators = [
            'competitive advantage', 'ahead of competitors', 'differentiate', 'edge',
            'outperform', 'market leader', 'first to market', 'innovative', 'cutting edge'
        ]

        if any(indicator in text_lower for indicator in competitive_indicators):
            return "VALUE TRIGGER: Competitive advantage interest! Expand strategic value: 'How important is it to stay ahead of competition? What's the cost of falling behind?'"

        # 5. GROWTH/SCALE EXPRESSIONS - Connect to business objectives
        growth_indicators = [
            'grow', 'scale', 'expand', 'increase', 'more customers', 'bigger',
            'growth', 'scaling', 'expansion', 'capacity', 'volume'
        ]

        if any(indicator in text_lower for indicator in growth_indicators):
            return "VALUE TRIGGER: Growth focus! Connect to scalability: 'As you grow, how would this solution scale with you? What's the value of handling 2x, 5x more volume?'"

        # 6. PROBLEM RESOLUTION VALUE - When they acknowledge pain relief
        resolution_indicators = [
            'fix that', 'solve the problem', 'eliminate', 'get rid of', 'no more',
            'won\'t have to deal with', 'takes care of', 'handles', 'addresses'
        ]

        if any(indicator in text_lower for indicator in resolution_indicators):
            return "VALUE TRIGGER: Problem resolution value! Amplify relief: 'What would it mean to your team to never deal with [problem] again? How would that change daily operations?'"

        # 7. TEAM/RESOURCE OPTIMIZATION - People value
        team_value_indicators = [
            'free up team', 'reduce workload', 'less manual work', 'team efficiency',
            'resource allocation', 'focus on', 'higher value work', 'strategic work'
        ]

        if any(indicator in text_lower for indicator in team_value_indicators):
            return "VALUE TRIGGER: Team optimization value! Quantify people impact: 'What could your team accomplish with [X] hours back per week? What strategic projects could they focus on instead?'"

        # 8. CUSTOMER/SATISFACTION VALUE - External impact
        customer_value_indicators = [
            'customer satisfaction', 'customer experience', 'better service',
            'happier customers', 'customer retention', 'client satisfaction'
        ]

        if any(indicator in text_lower for indicator in customer_value_indicators):
            return "VALUE TRIGGER: Customer value focus! Quantify external impact: 'How does improved customer satisfaction translate to business results? Revenue retention? Referrals?'"

        # 9. RISK MITIGATION VALUE - Security/compliance
        risk_indicators = [
            'reduce risk', 'compliance', 'security', 'avoid', 'prevent',
            'peace of mind', 'sleep better', 'worry less', 'confidence'
        ]

        if any(indicator in text_lower for indicator in risk_indicators):
            return "VALUE TRIGGER: Risk mitigation value! Quantify risk cost: 'What's the potential cost of [risk]? What would avoiding that risk be worth to the business?'"

        # ADVANCED VALUE PATTERN ANALYSIS

        # 10. IMPLIED VALUE - Subtle value expressions
        implied_value_patterns = [
            'makes sense', 'i like that', 'interesting', 'good point',
            'hadn\'t thought of that', 'that\'s smart', 'clever approach'
        ]

        if any(pattern in text_lower for pattern in implied_value_patterns):
            return "VALUE TRIGGER: Implied value detected! Make it explicit: 'I'm glad that resonates. Help me understand - what specifically appeals to you about this approach?'"

        # 11. COMPARISON VALUE - When they compare to alternatives
        comparison_indicators = [
            'compared to', 'versus', 'better than', 'unlike', 'different from',
            'current solution', 'what we have now', 'other options'
        ]

        if any(indicator in text_lower for indicator in comparison_indicators):
            return "VALUE TRIGGER: Comparison made! Build differentiation: 'What specific advantages do you see? How significant is that difference to your business?'"

        # 12. FUTURE STATE VISIONING - When they imagine outcomes
        vision_indicators = [
            'imagine if', 'would be great', 'dream scenario', 'ideal world',
            'perfect situation', 'what if we could', 'envision'
        ]

        if any(indicator in text_lower for indicator in vision_indicators):
            return "VALUE TRIGGER: Future visioning! Reinforce the vision: 'That sounds like an ideal outcome. Walk me through what that would mean for your business day-to-day.'"

        # CONTEXTUAL VALUE OPPORTUNITIES
        # Check recent conversation for setup opportunities

        if len(recent_segments) >= 2:
            recent_prospect_text = " ".join([s.text.lower() for s in recent_segments[-2:] if s.speaker == SpeakerType.PROSPECT])

            # They mentioned problems without quantifying impact
            problem_words = ['problem', 'issue', 'challenge', 'difficult', 'frustrating']
            if any(word in recent_prospect_text for word in problem_words) and 'cost' not in recent_prospect_text:
                return "VALUE OPPORTUNITY: Problems mentioned but not quantified. Ask: 'What's this problem costing you in time, money, or resources?'"

            # They expressed interest but haven't articulated value
            interest_words = ['interesting', 'good', 'like', 'sounds', 'looks']
            if any(word in recent_prospect_text for word in interest_words) and not any(word in recent_prospect_text for word in ['value', 'benefit', 'help', 'improve']):
                return "VALUE OPPORTUNITY: Interest shown but value not articulated. Ask: 'What specific benefits do you see this providing for your business?'"

        return None

    def detect_closing_advancement_coaching(self, text: str, speaker: SpeakerType, recent_segments: List[TranscriptSegment]) -> Optional[str]:
        """Advanced closing and advancement coaching - detect buying signals and closing opportunities"""
        if speaker != SpeakerType.PROSPECT:
            return None

        text_lower = text.lower()

        # CLOSING AND ADVANCEMENT TRIGGER DETECTION

        # 1. STRONG BUYING SIGNALS - Direct purchase intent
        strong_buying_signals = [
            'how do we get started', 'what are the next steps', 'when can we begin',
            'let\'s move forward', 'ready to proceed', 'want to do this',
            'how do we sign up', 'what\'s the process', 'when can we implement',
            'let\'s do it', 'sounds good', 'we want this', 'approved', 'green light'
        ]

        if any(signal in text_lower for signal in strong_buying_signals):
            return "CLOSING OPPORTUNITY: Strong buying signal detected! Take immediate action: 'Great! I'll get the agreement prepared. Are there any final questions before we get started?' Then outline specific next steps."

        # 2. BUDGET/PRICING ACCEPTANCE - Financial commitment
        budget_acceptance = [
            'budget approved', 'price is fine', 'cost works', 'fits our budget',
            'can afford', 'price is reasonable', 'worth the investment',
            'budget allocated', 'funding approved', 'money available'
        ]

        if any(signal in text_lower for signal in budget_acceptance):
            return "CLOSING OPPORTUNITY: Budget acceptance! Close now: 'Excellent! Since the budget works, shall we get the paperwork started so you can begin seeing results?'"

        # 3. TIMELINE/URGENCY EXPRESSIONS - Time-based buying signals
        urgency_signals = [
            'need this soon', 'urgent', 'asap', 'by end of quarter', 'deadline',
            'time sensitive', 'running out of time', 'need to decide quickly',
            'board meeting', 'presentation coming up', 'fiscal year'
        ]

        if any(signal in text_lower for signal in urgency_signals):
            return "CLOSING OPPORTUNITY: Urgency detected! Create action plan: 'Given your timeline, let's map out exactly what needs to happen. When do you need to have a decision made?'"

        # 4. AUTHORITY/DECISION MAKING - Decision power confirmation
        authority_signals = [
            'i can make this decision', 'my call', 'up to me', 'my decision',
            'i have authority', 'don\'t need approval', 'can sign off',
            'my budget', 'my project', 'my responsibility'
        ]

        if any(signal in text_lower for signal in authority_signals):
            return "CLOSING OPPORTUNITY: Decision authority confirmed! Move to close: 'Perfect! Since you can make the decision, what would you need to see to move forward today?'"

        # 5. IMPLEMENTATION PLANNING - Showing commitment
        implementation_signals = [
            'how would implementation work', 'what\'s the timeline', 'training needed',
            'rollout plan', 'go-live', 'deployment', 'setup process',
            'onboarding', 'getting started', 'launch plan'
        ]

        if any(signal in text_lower for signal in implementation_signals):
            return "ADVANCEMENT OPPORTUNITY: Implementation interest! Advance the sale: 'Great question - planning ahead shows you're serious about this. Let me walk you through our proven implementation process.'"

        # 6. TEAM/STAKEHOLDER BUY-IN - Internal support
        team_support = [
            'team loves this', 'everyone agrees', 'team is excited', 'full support',
            'unanimous decision', 'team consensus', 'everyone on board',
            'management approves', 'stakeholders agree'
        ]

        if any(signal in text_lower for signal in team_support):
            return "CLOSING OPPORTUNITY: Team buy-in achieved! Close with confidence: 'With full team support, this sounds like the perfect solution. Shall we get started?'"

        # 7. COMPARISON/COMPETITIVE ADVANTAGE - Preference signals
        preference_signals = [
            'better than', 'prefer this', 'like this more', 'clear winner',
            'obvious choice', 'stands out', 'best option', 'top choice',
            'beats the competition', 'superior to'
        ]

        if any(signal in text_lower for signal in preference_signals):
            return "CLOSING OPPORTUNITY: Preference established! Reinforce and close: 'I'm glad this stands out as the best fit. What do we need to do to make this your solution?'"

        # SOFT ADVANCEMENT OPPORTUNITIES

        # 8. INTEREST/ENGAGEMENT - Positive engagement
        engagement_signals = [
            'interesting', 'makes sense', 'good point', 'i see', 'understand',
            'that\'s helpful', 'good to know', 'appreciate that', 'thanks for explaining'
        ]

        # Only trigger if they show consistent engagement (multiple signals)
        if len([signal for signal in engagement_signals if signal in text_lower]) >= 2:
            return "ADVANCEMENT OPPORTUNITY: High engagement! Test for readiness: 'You seem interested - what questions do you have about moving forward?'"

        # 9. INFORMATION GATHERING - Research mode
        research_signals = [
            'need to research', 'look into this', 'compare options', 'due diligence',
            'need more information', 'want to think about it', 'review internally'
        ]

        if any(signal in text_lower for signal in research_signals):
            return "ADVANCEMENT OPPORTUNITY: Research mode detected. Guide the process: 'What specific information would help you make the best decision? Let me make sure you have everything you need.'"

        # 10. TRIAL/PILOT INTEREST - Soft commitment
        trial_signals = [
            'trial', 'pilot', 'test', 'proof of concept', 'small start',
            'try it out', 'see how it works', 'demo', 'sample'
        ]

        if any(signal in text_lower for signal in trial_signals):
            return "ADVANCEMENT OPPORTUNITY: Trial interest! Offer structured pilot: 'A pilot is a great way to prove value. Let me outline a 30-day pilot program that will give you clear ROI data.'"

        # CONTEXTUAL CLOSING ANALYSIS

        # 11. MULTIPLE POSITIVE SIGNALS - Pattern analysis
        if len(recent_segments) >= 3:
            recent_prospect_text = " ".join([s.text.lower() for s in recent_segments[-3:] if s.speaker == SpeakerType.PROSPECT])

            positive_words = ['good', 'great', 'yes', 'right', 'exactly', 'perfect', 'like', 'love', 'interested']
            positive_count = sum(1 for word in positive_words if word in recent_prospect_text)

            if positive_count >= 4:
                return "CLOSING OPPORTUNITY: Multiple positive signals detected! The momentum is strong - ask for the business: 'You seem very positive about this. What's the best way to move forward?'"

            # Check for decision-making language
            decision_words = ['decide', 'choice', 'option', 'consider', 'evaluate', 'select']
            if any(word in recent_prospect_text for word in decision_words):
                return "ADVANCEMENT OPPORTUNITY: Decision-making mode! Guide the decision: 'What factors are most important in your decision? Let me address each one specifically.'"

        # 12. FORWARD-LOOKING STATEMENTS - Future commitment
        future_signals = [
            'when we implement', 'after we start', 'once we have this',
            'when this is in place', 'after deployment', 'going forward',
            'in the future', 'down the road', 'long term'
        ]

        if any(signal in text_lower for signal in future_signals):
            return "CLOSING OPPORTUNITY: Future commitment language! Assume the sale: 'I love that you're thinking ahead to implementation. Let's make sure we get you started on the right timeline.'"

        # 13. INVESTMENT/ROI ACCEPTANCE - Value confirmed
        roi_acceptance = [
            'good investment', 'worth it', 'see the value', 'return on investment',
            'pays for itself', 'cost justified', 'makes financial sense'
        ]

        if any(signal in text_lower for signal in roi_acceptance):
            return "CLOSING OPPORTUNITY: ROI acceptance! Close on value: 'Since you see the clear ROI, let's get this implemented so you can start realizing those benefits. When would you like to begin?'"

        return None

    def detect_objection_handling_opportunities(self, text: str, speaker: SpeakerType, recent_segments: List[TranscriptSegment]) -> Optional[str]:
        """Advanced objection detection and handling coaching framework"""
        if speaker != SpeakerType.PROSPECT:
            return None

        text_lower = text.lower()

        # COMPREHENSIVE OBJECTION CATEGORIES
        # Each category has specific coaching strategies

        # 1. PRICE/BUDGET OBJECTIONS - Most common objections
        price_objections = {
            'explicit_price': [
                'too expensive', 'too costly', 'can\'t afford', 'price is too high', 'out of budget',
                'costs too much', 'price point', 'budget constraints', 'not in the budget'
            ],
            'value_questioning': [
                'not worth it', 'not sure about the value', 'roi unclear', 'return on investment',
                'justify the cost', 'why so expensive', 'seems overpriced'
            ],
            'comparison_shopping': [
                'cheaper option', 'competitors cost less', 'found it cheaper', 'better deal elsewhere',
                'more affordable solution', 'price comparison'
            ]
        }

        # 2. TIMING OBJECTIONS - Second most common
        timing_objections = {
            'not_ready': [
                'not ready', 'too early', 'not the right time', 'maybe later', 'next year',
                'still exploring', 'in research phase', 'need more time'
            ],
            'busy_priorities': [
                'too busy', 'other priorities', 'focused on', 'plate is full', 'bandwidth',
                'resources tied up', 'can\'t take on more'
            ],
            'internal_timing': [
                'waiting for approval', 'budget cycle', 'fiscal year', 'planning phase',
                'need buy-in', 'timing internally'
            ]
        }

        # 3. AUTHORITY OBJECTIONS - Decision making power
        authority_objections = {
            'need_approval': [
                'need approval', 'check with', 'run it by', 'discuss with team', 'need buy-in',
                'not my decision', 'someone else decides', 'up to my boss'
            ],
            'committee_decision': [
                'committee', 'team decision', 'group decision', 'multiple stakeholders',
                'consensus', 'board approval', 'executive decision'
            ],
            'procurement_process': [
                'procurement', 'rfp process', 'formal process', 'vendor selection',
                'evaluation process', 'approval workflow'
            ]
        }

        # 4. NEED OBJECTIONS - Questioning necessity
        need_objections = {
            'current_solution': [
                'current solution works', 'happy with current', 'existing system',
                'what we have is fine', 'no need to change', 'working well'
            ],
            'problem_questioning': [
                'not a priority', 'not a big issue', 'can live with it', 'not urgent',
                'manage without', 'not critical', 'nice to have'
            ],
            'diy_mentality': [
                'build internally', 'do it ourselves', 'handle in-house',
                'our team can do', 'develop our own'
            ]
        }

        # 5. TRUST/CREDIBILITY OBJECTIONS - Relationship based
        trust_objections = {
            'vendor_concerns': [
                'never heard of', 'small company', 'new company', 'not established',
                'track record', 'references', 'proven solution'
            ],
            'past_experiences': [
                'burned before', 'bad experience', 'vendor let us down', 'over-promised',
                'didn\'t deliver', 'poor support', 'implementation failed'
            ],
            'risk_aversion': [
                'too risky', 'safer option', 'proven solution', 'established player',
                'can\'t afford to fail', 'mission critical'
            ]
        }

        # 6. FEATURE/FIT OBJECTIONS - Product specific
        feature_objections = {
            'missing_features': [
                'doesn\'t have', 'missing', 'need something that', 'requires',
                'must have', 'deal breaker', 'critical feature'
            ],
            'integration_concerns': [
                'won\'t integrate', 'compatibility', 'work with existing', 'api',
                'systems integration', 'data migration'
            ],
            'performance_concerns': [
                'fast enough', 'scalable', 'handle volume', 'performance',
                'speed', 'capacity', 'uptime'
            ]
        }

        # OBJECTION DETECTION AND COACHING LOGIC
        # High-priority objections that need immediate attention

        # PRICE OBJECTIONS - Critical to address immediately
        for category, patterns in price_objections.items():
            if any(pattern in text_lower for pattern in patterns):
                if category == 'explicit_price':
                    return "PRICE OBJECTION: Acknowledge → Isolate → Reframe value. Say: 'I understand cost is a concern. If we could show clear ROI, would price still be an issue?'"
                elif category == 'value_questioning':
                    return "VALUE OBJECTION: Ask about cost of doing nothing. 'What's the cost of your current situation over the next 12 months?'"
                elif category == 'comparison_shopping':
                    return "COMPARISON OBJECTION: Focus on unique value. 'What specific capabilities are most important to you?' (Differentiate on value, not price)"

        # TIMING OBJECTIONS - Address urgency and consequences
        for category, patterns in timing_objections.items():
            if any(pattern in text_lower for pattern in patterns):
                if category == 'not_ready':
                    return "TIMING OBJECTION: Create urgency. Ask: 'What would need to happen for you to be ready?' Then address those specific conditions."
                elif category == 'busy_priorities':
                    return "PRIORITY OBJECTION: Connect to their priorities. 'What's the cost of waiting on your current priorities?' Tie your solution to their existing goals."
                elif category == 'internal_timing':
                    return "PROCESS OBJECTION: Work within their process. 'Help me understand your timeline. What can we do to prepare for that decision point?'"

        # AUTHORITY OBJECTIONS - Navigate decision process
        for category, patterns in authority_objections.items():
            if any(pattern in text_lower for pattern in patterns):
                if category == 'need_approval':
                    return "AUTHORITY OBJECTION: Include the decision maker. 'Who else would be involved in this decision? Can we include them in our next conversation?'"
                elif category == 'committee_decision':
                    return "COMMITTEE OBJECTION: Become their champion. 'What information would help you present this to the team? What questions will they ask?'"
                elif category == 'procurement_process':
                    return "PROCESS OBJECTION: Navigate the process. 'Help me understand your evaluation process. What criteria matter most?'"

        # NEED OBJECTIONS - Establish pain and urgency
        for category, patterns in need_objections.items():
            if any(pattern in text_lower for pattern in patterns):
                if category == 'current_solution':
                    return "STATUS QUO OBJECTION: Find hidden costs. 'What's working well? And where are the gaps or frustrations?' (Uncover dissatisfaction)"
                elif category == 'problem_questioning':
                    return "URGENCY OBJECTION: Amplify implications. 'What happens if this stays the same for another year? What opportunities might you miss?'"
                elif category == 'diy_mentality':
                    return "DIY OBJECTION: Address opportunity cost. 'What would your team focus on instead if this was handled automatically?'"

        # TRUST OBJECTIONS - Build credibility and reduce risk
        for category, patterns in trust_objections.items():
            if any(pattern in text_lower for pattern in patterns):
                if category == 'vendor_concerns':
                    return "CREDIBILITY OBJECTION: Provide social proof. Share a relevant customer story: 'Let me tell you how [similar company] addressed this same concern.'"
                elif category == 'past_experiences':
                    return "TRUST OBJECTION: Acknowledge and differentiate. 'I understand. What specifically went wrong? Here's how we ensure that doesn't happen.'"
                elif category == 'risk_aversion':
                    return "RISK OBJECTION: Offer proof and guarantees. 'What would make this feel safer? Would a pilot program or guarantee help?'"

        # FEATURE OBJECTIONS - Address fit and capabilities
        for category, patterns in feature_objections.items():
            if any(pattern in text_lower for pattern in patterns):
                if category == 'missing_features':
                    return "FEATURE OBJECTION: Understand priority. 'Help me understand why that specific feature is important. What business problem does it solve?'"
                elif category == 'integration_concerns':
                    return "INTEGRATION OBJECTION: Address technically. 'Let's discuss your tech stack. Our integration team can walk through exactly how this works.'"
                elif category == 'performance_concerns':
                    return "PERFORMANCE OBJECTION: Provide specifics. 'What performance requirements do you have? Let me show you our benchmarks and SLAs.'"

        # SOFT OBJECTIONS AND HESITATION PATTERNS
        soft_objections = [
            'not sure', 'maybe', 'we\'ll see', 'need to think', 'sounds interesting but',
            'i don\'t know', 'not convinced', 'skeptical', 'hesitant', 'concerned about'
        ]

        if any(soft in text_lower for soft in soft_objections):
            return "SOFT OBJECTION: Dig deeper. 'What specifically concerns you?' or 'What would need to be different?' (Uncover the real objection)"

        # MULTIPLE OBJECTIONS - Advanced handling
        # Check if this is a pattern of objections (smokescreen)
        recent_text = " ".join([s.text.lower() for s in recent_segments[-3:] if s.speaker == SpeakerType.PROSPECT])
        objection_count = 0
        all_patterns = []
        for obj_dict in [price_objections, timing_objections, authority_objections, need_objections, trust_objections, feature_objections]:
            for category_patterns in obj_dict.values():
                all_patterns.extend(category_patterns)

        for pattern in all_patterns:
            if pattern in recent_text:
                objection_count += 1

        if objection_count >= 3:
            return "MULTIPLE OBJECTIONS: Potential smokescreen. Ask: 'It sounds like you have several concerns. What's the real issue here?'"

        return None

class SalesCoach:
    """AI-powered sales coaching using Claude API"""

    def __init__(self):
        # Claude API configuration - IMPORTANT: Set your API key as environment variable
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            safe_print("⚠️ WARNING: ANTHROPIC_API_KEY not set. AI suggestions will be disabled.")
            safe_print("Set ANTHROPIC_API_KEY environment variable to enable AI coaching.")

        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")

        # Track suggestion generation
        self.last_suggestion_time = 0
        self.suggestion_cooldown = 60.0  # 60 seconds between suggestions - be very conservative
        self.recent_suggestions = []
        self.max_suggestion_history = 5

        # Enhanced caching and quality scoring
        self.suggestion_cache = {}  # Hash -> Suggestion objects
        self.suggestion_scores = {}  # suggestion_id -> quality score
        self.duplicate_threshold = 0.8  # Similarity threshold for duplicates
        self.context_signatures = set()  # Track similar contexts

        # Performance optimizations
        self.batch_requests = []  # Queue for batching API calls
        self.batch_timeout = 2.0  # seconds to wait before sending batch
        self.last_batch_time = 0
        self.circuit_breaker_failures = 0
        self.circuit_breaker_threshold = 3
        self.circuit_breaker_reset_time = 60  # seconds

    def get_phase_specific_prompt(self, phase: str, conversation_history: List[str],
                                  prospect_last_statement: str, call_config: Dict = None) -> str:
        """Generate phase-specific sales coaching prompts"""

        # Build call configuration context
        config_context = ""
        if call_config:
            config_context = f"""
        CALL OBJECTIVES AND CONTEXT:
        - Call Type: {call_config.get('call_type', 'unknown')}
        - Primary Objective: {call_config.get('primary_objective', 'not specified')}
        - Key Success Metrics: {call_config.get('success_metrics', 'not specified')}
        - Prospect Background: {call_config.get('prospect_background', 'not provided')}
        - Expected Challenges: {call_config.get('challenges', 'not identified')}
        - Preparation Notes: {call_config.get('notes', 'none')}

        TAILOR ALL COACHING to align with these specific objectives and context.
        """

        base_context = f"""You are an expert sales coach providing VERY SELECTIVE real-time guidance during a live sales conversation.
        The conversation is currently in the {phase} phase.
        {config_context}
        Recent conversation context:
        {chr(10).join(conversation_history[-3:])}

        Prospect's last statement: "{prospect_last_statement}"

        IMPORTANT: Only provide suggestions for HIGH-VALUE moments. Be extremely selective.
        Focus suggestions on achieving the PRIMARY OBJECTIVE and addressing the EXPECTED CHALLENGES.

        Generate 1-2 ONLY the most critical, actionable suggestions for the sales rep. Each suggestion should be:
        - A genuine game-changing opportunity (not routine conversation)
        - Immediately actionable and specific
        - Based on what the prospect JUST said
        - Focused on advancing toward the PRIMARY OBJECTIVE
        - Concise (one clear sentence each)
        - Directly relevant to the call type and success metrics

        If this is not a high-value moment warranting coaching, return an empty array: []

        Format your response as a JSON array of strings:
        ["suggestion 1", "suggestion 2"] or []
        """

        if phase == "opening":
            call_type_guidance = ""
            if call_config and call_config.get('goal'):
                call_goal = call_config.get('goal')

                # DISCOVERY CALLS - Mirroring is CRITICAL
                if call_goal == "Discovery_Initial":
                    call_type_guidance = """- PRIMARY FOCUS: MIRRORING - This is the #1 coaching priority for building rapport
            - Use their exact words when you respond back to them
            - Mirror their emotions and energy level
            - Ask about their background and current situation
            - Set expectation: 'I'd like to learn about your business'"""
                elif call_goal == "Discovery_Deep":
                    call_type_guidance = """- PRIMARY FOCUS: MIRRORING PAIN POINTS - Echo their frustrations back to them
            - Mirror their language when they describe problems
            - Dig into implications: 'So when [their problem] happens, what impact does that have?'
            - Use SPIN methodology heavily"""
                elif call_goal == "Discovery_Qualification":
                    call_type_guidance = """- Mirror their decision-making process language
            - Mirror their urgency and timeline language
            - Ask about budget using their financial terms
            - Confirm authority levels using their organizational language"""

                # DEMO CALLS
                elif call_goal == "Demo_Technical":
                    call_type_guidance = """- Mirror their technical language and terminology
            - Use their specific use cases in your demo
            - Focus on features that solve their stated problems
            - Mirror their workflow and process language"""
                elif call_goal == "Demo_Executive":
                    call_type_guidance = """- Mirror their business language (ROI, efficiency, growth)
            - Focus on strategic value and competitive advantage
            - Use their success metrics in your presentation
            - Mirror their leadership communication style"""

                # CLOSING CALLS
                elif call_goal == "Close_Proposal":
                    call_type_guidance = """- Mirror their evaluation criteria language
            - Use their priority language when presenting benefits
            - Address their specific concerns using their terminology
            - Mirror their decision timeline language"""
                elif call_goal == "Close_Negotiation":
                    call_type_guidance = """- Mirror their negotiation style (collaborative vs competitive)
            - Use their budget and pricing language
            - Mirror their urgency and timeline expressions
            - Echo their value and outcome language"""

                # FOLLOW-UP CALLS
                elif call_goal == "Follow_up_Proposal":
                    call_type_guidance = """- Reference and mirror language from previous calls
            - Mirror their current priorities and concerns
            - Use their internal process language
            - Mirror their timeline and next steps language"""
                elif call_goal == "Follow_up_Objections":
                    call_type_guidance = """- Mirror their specific objection language back to them
            - Acknowledge their concerns using their exact words
            - Use their success criteria when addressing objections
            - Mirror their decision-making process"""

            return base_context + f"""
            Opening Phase Coaching:
            - Build rapport through active listening and mirroring
            - Set appropriate call expectations and agenda
            - Establish credibility without being pushy
            {call_type_guidance}"""

        elif phase == "discovery":
            return base_context + """
            SPIN SELLING METHODOLOGY - Discovery Phase Excellence:

            FOLLOW THIS PROVEN SEQUENCE FOR MAXIMUM EFFECTIVENESS:

            🎯 SITUATION QUESTIONS (Foundation - 20-30% of questions)
            PURPOSE: Build understanding of their current state
            EXAMPLES:
            - "Walk me through your current process for [topic]"
            - "How many people are involved in this process?"
            - "What systems/tools are you currently using?"
            - "How long have you been doing it this way?"
            - "Who's responsible for [specific aspect]?"

            🔍 PROBLEM QUESTIONS (Core Discovery - 30-40% of questions)
            PURPOSE: Uncover dissatisfaction and pain points
            EXAMPLES:
            - "What challenges do you face with this approach?"
            - "Where do you see bottlenecks in the process?"
            - "What's frustrating about the current situation?"
            - "What's not working as well as you'd like?"
            - "Where are you losing time/money/efficiency?"

            💥 IMPLICATION QUESTIONS (Pain Amplification - 20-30% of questions)
            PURPOSE: Help them understand the COST of problems
            EXAMPLES:
            - "What impact does this have on your team's productivity?"
            - "How does this affect your ability to hit goals?"
            - "What happens if this problem continues for another year?"
            - "How is this impacting customer satisfaction?"
            - "What's this costing you in terms of time/resources?"

            💡 NEED-PAYOFF QUESTIONS (Vision Building - 15-25% of questions)
            PURPOSE: Get them selling themselves on the solution
            EXAMPLES:
            - "How important would it be to eliminate this bottleneck?"
            - "What would improvement in this area mean for your business?"
            - "How would your team benefit from a more efficient process?"
            - "What value would you see from solving this problem?"
            - "How would this help you achieve your goals faster?"

            🏆 ADVANCED SPIN TECHNIQUES:

            LISTEN FOR BUYING SIGNALS:
            - Problems they're eager to discuss
            - Emotional words (frustrated, excited, concerned)
            - Time/money impact statements
            - References to goals/objectives

            CONVERSATION CONTROL:
            - Ask follow-up questions to go deeper
            - Use their exact words in your next question
            - Pause after questions - let them think
            - Build on their answers progressively

            DISCOVERY SUCCESS METRICS:
            - Prospect talks 60-70% of the time
            - You uncover 3-5 specific problems
            - They mention impact/consequences
            - They express desire for change
            - You understand their decision process

            Remember: Questions are more powerful than statements in discovery!
            """

        elif phase == "demo":
            return base_context + """
            Focus on:
            - Connecting features directly to their stated needs
            - Using benefit statements, not just feature lists
            - Asking confirmation questions ("Does this address your concern about...")
            - Getting micro-commitments and engagement
            """

        elif phase == "objection":
            return base_context + """
            OBJECTION HANDLING FRAMEWORK - Critical Phase:

            STEP 1: ACKNOWLEDGE + LISTEN
            - "I understand that's a concern"
            - Don't get defensive or argue
            - Let them fully express the objection

            STEP 2: CLARIFY + ISOLATE
            - "Help me understand what specifically concerns you"
            - "Is this the only concern, or are there others?"
            - Identify if it's a real objection or just a request for information

            STEP 3: ADDRESS SYSTEMATICALLY:

            PRICE OBJECTIONS:
            - Don't lower price immediately - build value first
            - Ask about cost of doing nothing
            - Present ROI and payback calculations
            - "What would need to be true for this to make financial sense?"

            TIMING OBJECTIONS:
            - Create urgency by showing cost of delay
            - "What would need to happen for timing to work?"
            - Offer phased implementation or pilot programs

            AUTHORITY OBJECTIONS:
            - "Who else is involved in this decision?"
            - "What information would help you present this internally?"
            - Offer to speak with the decision maker

            NEED/FIT OBJECTIONS:
            - Revisit pain points and implications
            - "What happens if this problem persists?"
            - Use case studies of similar companies

            TRUST/CREDIBILITY OBJECTIONS:
            - Provide references and testimonials
            - Offer guarantees or pilot programs
            - Share specific success metrics

            STEP 4: CONFIRM + ADVANCE
            - "Does that address your concern?"
            - "What questions do you still have?"
            - "What would be the next logical step?"

            Remember: Most objections are requests for more information, not final rejections.
            """

        elif phase == "closing":
            return base_context + """
            Focus on:
            - Identifying specific next steps
            - Creating urgency around decision-making
            - Asking for commitment to move forward
            - Addressing any final concerns before closing
            """

        else:  # unknown phase
            return base_context + """
            Provide general sales best practices:
            - Ask open-ended questions to better understand their needs
            - Listen actively and acknowledge their responses
            - Look for opportunities to provide value
            - Guide the conversation toward next steps
            """

    def generate_context_signature(self, phase: str, conversation_history: List[str],
                                   prospect_statement: str) -> str:
        """Generate a signature for similar conversation contexts"""
        context_text = f"{phase}|{prospect_statement}|{len(conversation_history)}"
        return hashlib.md5(context_text.encode()).hexdigest()[:8]

    def create_suggestion_objects(self, suggestions_data: List[Dict], phase: str) -> List[Suggestion]:
        """Create enhanced Suggestion objects from API response"""
        suggestion_objects = []
        current_time = time.time()

        for idx, item in enumerate(suggestions_data):
            if isinstance(item, dict):
                suggestion = Suggestion(
                    id=f"sugg_{current_time:.0f}_{idx:03d}",
                    technique=item.get("technique", "general_coaching"),
                    priority=item.get("priority", "medium"),
                    text=item.get("text", str(item)),
                    rationale=item.get("rationale", "AI-generated coaching suggestion"),
                    phase=phase,
                    timestamp=current_time
                )
            else:
                # Handle string suggestions (fallback compatibility)
                suggestion = Suggestion(
                    id=f"sugg_{current_time:.0f}_{idx:03d}",
                    technique="general_coaching",
                    priority="medium",
                    text=str(item),
                    rationale="Context-aware sales coaching",
                    phase=phase,
                    timestamp=current_time
                )
            suggestion_objects.append(suggestion)
        return suggestion_objects

    def is_duplicate_suggestion(self, new_suggestion: Suggestion) -> bool:
        """Check if suggestion is too similar to recent ones"""
        new_text_lower = new_suggestion.text.lower()

        for recent_text in self.recent_suggestions:
            if isinstance(recent_text, str):
                recent_lower = recent_text.lower()
            else:
                recent_lower = str(recent_text).lower()

            # Simple similarity check - could be enhanced with more sophisticated NLP
            if len(set(new_text_lower.split()) & set(recent_lower.split())) / max(len(new_text_lower.split()), 1) > self.duplicate_threshold:
                return True
        return False

    def is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open due to failures"""
        if self.circuit_breaker_failures >= self.circuit_breaker_threshold:
            if time.time() - self.last_suggestion_time > self.circuit_breaker_reset_time:
                # Reset circuit breaker after timeout
                self.circuit_breaker_failures = 0
                safe_print("🔄 Circuit breaker reset - resuming API calls")
                return False
            return True
        return False

    async def generate_suggestions(self, conversation_intelligence: Dict[str, Any]) -> Optional[List[Dict]]:
        """Generate AI coaching suggestions using Claude API"""

        if not self.api_key:
            return None

        # Check circuit breaker
        if self.is_circuit_breaker_open():
            safe_print("⚡ Circuit breaker open - skipping API call")
            return None

        current_time = time.time()
        if current_time - self.last_suggestion_time < self.suggestion_cooldown:
            return None

        try:
            # Extract conversation context
            phase = conversation_intelligence.get("conversation_state", {}).get("phase", "unknown")
            segment = conversation_intelligence.get("segment", {})
            prospect_statement = segment.get("text", "") if segment.get("speaker") == "prospect" else ""

            # Get actual conversation history
            conversation_history = conversation_intelligence.get("conversation_history", [])
            if not conversation_history:
                # Fallback to minimal context
                conversation_history = [
                    f"Sales Rep: [Current conversation in progress]",
                    f"Prospect: {prospect_statement}" if prospect_statement else "Prospect: [listening]"
                ]

            # Extract call configuration
            call_config = conversation_intelligence.get("call_config", None)

            # Generate phase-specific prompt
            base_prompt = self.get_phase_specific_prompt(phase, conversation_history, prospect_statement, call_config)

            # Enhanced prompt for structured JSON response
            prompt = base_prompt + f"""

IMPORTANT: Respond with ONLY a JSON array of suggestion objects. Each suggestion must have this exact format:
[
  {{
    "technique": "technique_name",
    "priority": "high|medium|low",
    "text": "Actual suggestion text",
    "rationale": "Brief explanation of why this suggestion helps"
  }}
]

Available techniques: mirroring_expansion, quantification_probe, implication_question, need_payoff_question, empathy_statement, trial_close, objection_handling, value_reinforcement, next_step_probe, pain_point_expansion

Priority guidelines:
- HIGH: Critical conversation moments, objections, closing opportunities
- MEDIUM: Good coaching opportunities, skill development
- LOW: General best practices

Generate 2-3 specific, actionable suggestions based on the current conversation context."""

            # Prepare Claude API request
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }

            payload = {
                "model": self.model,
                "max_tokens": 500,
                "temperature": 0.7,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            # Make API request
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        content = result.get("content", [{}])[0].get("text", "")

                        # Parse JSON response and create enhanced suggestions
                        try:
                            suggestions_data = json.loads(content)
                            if isinstance(suggestions_data, list) and len(suggestions_data) > 0:
                                # Create enhanced suggestion objects
                                suggestion_objects = self.create_suggestion_objects(suggestions_data, phase)

                                # Filter duplicates
                                unique_suggestions = []
                                for suggestion in suggestion_objects:
                                    if not self.is_duplicate_suggestion(suggestion):
                                        unique_suggestions.append(suggestion)

                                if unique_suggestions:
                                    self.last_suggestion_time = current_time

                                    # Update caches
                                    context_signature = self.generate_context_signature(phase, conversation_history, prospect_statement)
                                    self.context_signatures.add(context_signature)

                                    # Store in suggestion cache and recent list
                                    for suggestion in unique_suggestions:
                                        self.suggestion_cache[suggestion.id] = suggestion
                                        self.recent_suggestions.append(suggestion.text)

                                    # Maintain history limits
                                    if len(self.recent_suggestions) > self.max_suggestion_history:
                                        self.recent_suggestions = self.recent_suggestions[-self.max_suggestion_history:]

                                    # Return formatted suggestion data for WebSocket
                                    formatted_suggestions = [
                                        {
                                            "id": s.id,
                                            "technique": s.technique,
                                            "priority": s.priority,
                                            "text": s.text,
                                            "rationale": s.rationale
                                        }
                                        for s in unique_suggestions
                                    ]

                                    safe_print(f"🎯 Generated {len(unique_suggestions)} unique AI coaching suggestions for {phase} phase")
                                    if session_logger:
                                        session_logger.log_suggestions_generated(formatted_suggestions, phase)
                                    return formatted_suggestions
                                else:
                                    safe_print("⚠️ All suggestions were duplicates - skipping")
                                    return None
                            else:
                                safe_print("⚠️ Claude API returned invalid suggestion format")
                                return None

                        except json.JSONDecodeError:
                            # Fallback: treat response as plain text and split into suggestions
                            lines = [line.strip() for line in content.split('\n') if line.strip()]
                            if lines:
                                safe_print(f"🎯 Generated {len(lines)} AI coaching suggestions (text format)")
                                return lines[:3]  # Take first 3 lines
                            return None

                    else:
                        self.circuit_breaker_failures += 1
                        safe_print(f"❌ Claude API error: {response.status} - {await response.text()}")
                        safe_print(f"⚠️ Circuit breaker failures: {self.circuit_breaker_failures}/{self.circuit_breaker_threshold}")
                        return None

        except asyncio.TimeoutError:
            self.circuit_breaker_failures += 1
            safe_print("⏱️ Claude API request timed out")
            safe_print(f"⚠️ Circuit breaker failures: {self.circuit_breaker_failures}/{self.circuit_breaker_threshold}")
            return None
        except Exception as e:
            self.circuit_breaker_failures += 1
            safe_print(f"❌ Error generating AI suggestions: {e}")
            safe_print(f"⚠️ Circuit breaker failures: {self.circuit_breaker_failures}/{self.circuit_breaker_threshold}")
            return None

# Global model instance (loaded lazily)
whisper_model = None
model_lock = threading.Lock()

def load_whisper_model():
    global whisper_model
    with model_lock:
        if whisper_model is not None:
            return whisper_model

        safe_print("Loading Whisper model on demand...")
        try:
            # Use only regular OpenAI whisper for simplicity
            import whisper
            whisper_model = whisper.load_model("small")
            safe_print("Regular whisper small model loaded successfully!")
            return whisper_model
        except Exception as e:
            safe_print(f"Failed to load Whisper model: {e}")
            return None

class WhisperTranscriber:
    def __init__(self):
        # Don't load model in constructor - load on demand

        # Audio buffer for accumulating chunks
        self.audio_buffer = bytearray()
        self.sample_rate = 48000
        self.channels = 2
        self.chunk_duration = 3.0  # Process every 3 seconds
        self.min_chunk_size = int(self.sample_rate * self.channels * 2 * self.chunk_duration)

        # Duplicate detection to prevent repetition
        self.recent_transcripts = []
        self.max_recent_history = 5

        # Conversation intelligence
        self.conversation_intel = ConversationIntelligence()
        self.last_speaker = None

        # AI Sales Coach
        self.sales_coach = SalesCoach()

        # Call configuration for goal-driven coaching
        self.call_config = None

    def get_conversation_history(self) -> List[str]:
        """Get formatted conversation history for AI context"""
        history = []
        for segment in self.conversation_intel.state.recent_segments[-5:]:  # Last 5 segments
            speaker_label = "Sales Rep" if segment.speaker == SpeakerType.SALES_REP else "Prospect"
            history.append(f"{speaker_label}: {segment.text}")
        return history
        
    def process_audio_chunk(self, audio_data):
        """Process accumulated audio when we have enough data"""
        try:
            model = load_whisper_model()
            if model is None:
                safe_print("No Whisper model available")
                return ""
            
            # Save audio to permanent directory - much more reliable!
            import time

            # Create audio directory if it doesn't exist
            audio_dir = "audio_files"
            if not os.path.exists(audio_dir):
                os.makedirs(audio_dir)

            # Use timestamp for unique filename
            timestamp = int(time.time() * 1000)
            audio_path = os.path.join(audio_dir, f"audio_{timestamp}.wav")

            try:
                # Write WAV file
                with wave.open(audio_path, 'wb') as wav_file:
                    wav_file.setnchannels(self.channels)
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(self.sample_rate)
                    wav_file.writeframes(audio_data)

                safe_print(f"DEBUG: Saved audio to {audio_path}")

                # Use regular whisper - much simpler and more reliable
                safe_print("DEBUG: Starting transcription...")
                try:
                    # Enhanced transcription with better options for accuracy
                    result = model.transcribe(
                        audio_path,
                        language="en",
                        task="transcribe",
                        fp16=False,  # Use FP32 for better accuracy
                        temperature=0.0,  # Deterministic output
                        no_speech_threshold=0.8,  # Be more aggressive about filtering silence
                        logprob_threshold=-1.0,  # Accept lower confidence transcriptions
                        compression_ratio_threshold=2.4  # Handle compressed audio better
                    )
                    transcription_text = result['text']

                    # Basic post-processing to clean up transcript
                    if transcription_text:
                        transcription_text = transcription_text.strip()

                        # Filter out repetitive patterns (Whisper hallucination during silence)
                        def detect_repetitive_pattern(text):
                            """Detect if text contains repetitive patterns that indicate hallucination"""
                            if len(text) < 20:
                                return False

                            # Check for repeating short phrases
                            words = text.lower().split()
                            if len(words) < 5:
                                return False

                            # Look for patterns like "a little bit of a little bit of"
                            for i in range(len(words) - 8):  # Check 4-word patterns
                                pattern = ' '.join(words[i:i+4])
                                remaining_text = ' '.join(words[i+4:])
                                # If the 4-word pattern repeats 3+ times, it's likely hallucination
                                if remaining_text.count(pattern) >= 2:
                                    safe_print(f"DEBUG: Detected repetitive pattern: '{pattern}' - filtering out")
                                    return True

                            # Check for single word repetition (like "and and and and")
                            for word in set(words):
                                if len(word) > 2 and words.count(word) > 5:
                                    safe_print(f"DEBUG: Detected excessive word repetition: '{word}' - filtering out")
                                    return True

                            return False

                        # Filter out repetitive patterns
                        if detect_repetitive_pattern(transcription_text):
                            transcription_text = ""  # Skip this transcript entirely
                        else:
                            # Remove common transcription artifacts
                            transcription_text = transcription_text.replace("  ", " ")  # Multiple spaces
                            transcription_text = transcription_text.replace("...", ".")  # Multiple dots
                            # Remove leading/trailing punctuation artifacts
                            while transcription_text.startswith((' ', ',', '.', '?', '!')):
                                transcription_text = transcription_text[1:]

                        # Duplicate detection - check if this transcript is very similar to recent ones
                        is_duplicate = False
                        if transcription_text:
                            for recent in self.recent_transcripts:
                                # Check for exact match or very similar (allowing for minor variations)
                                if (transcription_text == recent or
                                    (len(transcription_text) > 3 and transcription_text in recent) or
                                    (len(recent) > 3 and recent in transcription_text)):
                                    is_duplicate = True
                                    safe_print(f"DEBUG: Duplicate detected - '{transcription_text}' matches recent '{recent}'")
                                    break

                        if is_duplicate:
                            transcription_text = ""  # Skip duplicate
                        else:
                            # Add to recent history
                            self.recent_transcripts.append(transcription_text)
                            if len(self.recent_transcripts) > self.max_recent_history:
                                self.recent_transcripts.pop(0)

                            # Extract stereo audio channels for speaker analysis
                            audio_numpy = np.frombuffer(audio_data, dtype=np.int16)
                            if self.channels == 2:
                                # Separate stereo channels
                                left_channel = audio_numpy[0::2].astype(np.float32) / 32768.0  # Mic
                                right_channel = audio_numpy[1::2].astype(np.float32) / 32768.0  # Tab
                            else:
                                # Mono audio - treat as mic
                                left_channel = audio_numpy.astype(np.float32) / 32768.0
                                right_channel = np.zeros_like(left_channel)

                            # Add conversation intelligence
                            conversation_data = self.conversation_intel.add_transcript_segment(
                                transcription_text, "stereo", left_channel, right_channel
                            )

                            if conversation_data:
                                current_speaker = conversation_data['segment']['speaker']
                                speaker_changed = self.last_speaker != current_speaker

                                # Only log speaker changes and important events
                                if speaker_changed:
                                    safe_print(f"🎤 Speaker change: {current_speaker}")
                                    self.last_speaker = current_speaker

                                # Always log phase changes and suggestion readiness
                                phase = conversation_data['conversation_state']['phase']
                                if hasattr(self, '_last_phase') and self._last_phase != phase:
                                    safe_print(f"📊 Conversation phase: {phase}")
                                elif not hasattr(self, '_last_phase'):
                                    safe_print(f"📊 Conversation phase: {phase}")
                                self._last_phase = phase

                                if conversation_data['suggestion_ready']:
                                    safe_print(f"🤖 AI suggestion ready!")

                                # Store conversation data for WebSocket response
                                self._last_conversation_data = conversation_data

                    safe_print(f"DEBUG: Transcription result: {transcription_text[:50]}")

                    # Clean up the audio file only after successful transcription
                    try:
                        os.unlink(audio_path)
                        safe_print("DEBUG: Cleaned up audio file")
                    except:
                        safe_print("DEBUG: Could not clean up audio file (file may be in use)")

                except Exception as transcribe_error:
                    safe_print(f"DEBUG: Transcription failed: {transcribe_error}")
                    safe_print(f"DEBUG: Audio file preserved at: {audio_path}")
                    transcription_text = "Transcription failed"

            except Exception as file_error:
                safe_print(f"DEBUG: File creation failed: {file_error}")
                transcription_text = "File creation failed"

            return transcription_text.strip()
                
        except Exception as e:
            safe_print(f"Transcription error: {e}")
            return ""
    
    def add_audio_chunk(self, chunk):
        """Add audio chunk to buffer and process when ready"""
        self.audio_buffer.extend(chunk)
        
        # Process when we have enough audio
        if len(self.audio_buffer) >= self.min_chunk_size:
            # Take chunk for processing
            chunk_data = bytes(self.audio_buffer[:self.min_chunk_size])
            # Reduce overlap from 50% to 25% to minimize repetition while maintaining continuity
            self.audio_buffer = self.audio_buffer[self.min_chunk_size * 3 // 4:]  # 25% overlap

            return self.process_audio_chunk(chunk_data)

        return ""

async def generate_ai_suggestions_if_ready(transcriber, websocket):
    """Generate and send AI suggestions when conditions are right"""
    try:
        # Check if we have conversation intelligence data
        if not hasattr(transcriber, '_last_conversation_data'):
            return

        conversation_data = transcriber._last_conversation_data
        if not conversation_data or not conversation_data.get("suggestion_ready"):
            return

        # Generate AI suggestions with actual conversation history
        conversation_data_with_history = conversation_data.copy()
        conversation_data_with_history["conversation_history"] = transcriber.get_conversation_history()
        conversation_data_with_history["call_config"] = transcriber.call_config

        suggestions = await transcriber.sales_coach.generate_suggestions(conversation_data_with_history)
        if not suggestions:
            return

        # Extract conversation context for enhanced message format
        conversation_state = conversation_data.get("conversation_state", {})
        segment = conversation_data.get("segment", {})

        # Send enhanced suggestions message to the extension
        response = {
            "type": "suggestions",
            "timestamp": time.time(),
            "conversation_context": {
                "phase": conversation_state.get("phase", "unknown"),
                "last_speaker": segment.get("speaker", "unknown"),
                "key_topics": conversation_state.get("topic_keywords", [])
            },
            "suggestions": suggestions
        }

        try:
            await websocket.send(json.dumps(response))
            suggestion_count = len(suggestions)
            high_priority_count = len([s for s in suggestions if s.get("priority") == "high"])
            safe_print(f"💡 Sent {suggestion_count} AI suggestions ({high_priority_count} high priority) for {conversation_state.get('phase', 'unknown')} phase")
        except Exception as send_error:
            safe_print(f"❌ Failed to send AI suggestion: {send_error}")

    except Exception as e:
        safe_print(f"❌ Error in AI suggestion generation: {e}")

async def handle_websocket(websocket):
    """Handle WebSocket connection from Node.js server"""
    try:
        safe_print(f"New WebSocket connection: {websocket.remote_address}")
    except UnicodeEncodeError:
        safe_print("New WebSocket connection (address encoding issue)")

    safe_print("DEBUG: Connection established, waiting for messages...")

    # Initialize session logger for this connection
    global session_logger
    session_logger = SessionLogger()

    transcriber = WhisperTranscriber()  # Model will load on demand
    call_config = None  # Store call configuration
    
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Audio data received
                safe_print(f"DEBUG: Received {len(message)} bytes of audio data")
                transcript = transcriber.add_audio_chunk(message)

                if transcript:
                    # Get conversation intelligence data for the transcript
                    intel_data = getattr(transcriber, '_last_conversation_data', None)

                    # Send transcription back to server with conversation intelligence
                    response = {
                        "type": "transcript",
                        "text": transcript,
                        "is_final": True,
                        "timestamp": time.time(),
                        "conversation_intelligence": intel_data
                    }

                    safe_print(f"DEBUG: About to send transcript: {transcript[:50]}...")
                    try:
                        await websocket.send(json.dumps(response))
                        safe_print(f"DEBUG: Successfully sent transcript to extension")
                        # Use safe encoding for printing
                        safe_transcript = transcript.encode('ascii', 'replace').decode('ascii')
                        safe_print(f"Transcribed: {safe_transcript}")

                        # Log transcript to file
                        if session_logger and intel_data:
                            segment = intel_data.get('segment', {})
                            speaker = segment.get('speaker', 'unknown')
                            confidence = segment.get('confidence')
                            session_logger.log_transcript(speaker, transcript, confidence, True)

                        # Generate AI suggestions if conditions are right
                        await generate_ai_suggestions_if_ready(transcriber, websocket)

                    except Exception as send_error:
                        safe_print(f"DEBUG: Failed to send transcript: {send_error}")
                    except UnicodeEncodeError:
                        safe_print(f"Transcribed: [Unicode content - {len(transcript)} chars]")

            elif isinstance(message, str):
                # Text message received (e.g., call configuration)
                try:
                    message_data = json.loads(message)
                    if message_data.get('type') == 'call_config':
                        call_config = message_data.get('config', {})
                        safe_print(f"Call configuration received: {call_config.get('goal', 'Unknown')} call")
                        # Store configuration in transcriber for use in AI suggestions
                        transcriber.call_config = call_config
                except json.JSONDecodeError:
                    safe_print(f"Received invalid JSON message: {message[:100]}")
                    
            else:
                # Text message (control)
                try:
                    data = json.loads(message)
                    if data.get("type") == "config":
                        # Update configuration
                        transcriber.sample_rate = data.get("sample_rate", 48000)
                        transcriber.channels = data.get("channels", 2)
                        safe_print(f"Config updated: {transcriber.sample_rate}Hz, {transcriber.channels}ch")
                except json.JSONDecodeError:
                    pass
                    
    except websockets.exceptions.ConnectionClosed:
        try:
            safe_print(f"Connection closed: {websocket.remote_address}")
        except UnicodeEncodeError:
            safe_print("Connection closed (address encoding issue)")

        # Log session summary when connection closes
        if session_logger:
            session_logger.log_session_summary()
    except Exception as e:
        try:
            safe_print(f"WebSocket error: {e}")
        except UnicodeEncodeError:
            safe_print(f"WebSocket error: [Unicode error - {type(e).__name__}]")

async def main():
    safe_print("Starting Local Whisper Transcription Server", flush=True)
    safe_print("Listening on ws://localhost:3003", flush=True)
    safe_print("Server will start and load Whisper model on first connection...", flush=True)

    server = await websockets.serve(handle_websocket, "localhost", 3003)
    safe_print("WebSocket server is now accepting connections!", flush=True)
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
