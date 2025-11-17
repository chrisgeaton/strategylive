#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sales Expert Agent - Development Quality Assurance
Validates and improves coaching suggestions for optimal sales effectiveness
"""

import asyncio
import aiohttp
import json
import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("python-dotenv not installed. Using system environment variables only.")

@dataclass
class CoachingEvaluation:
    """Evaluation result from sales expert agent"""
    timing_score: int  # 1-10
    technique_accuracy: int  # 1-10
    effectiveness_prediction: int  # 1-10
    overall_score: int  # 1-10
    would_top_performer_use: bool
    risk_assessment: str  # "low", "medium", "high"
    issues: List[str]
    improvements: List[str]
    better_approach: Optional[str]
    reasoning: str

@dataclass
class CoachingScenario:
    """Test scenario for coaching evaluation"""
    conversation_context: str
    transcript_snippet: str
    our_suggestion: str
    call_goal: str
    conversation_phase: str
    speaker: str  # "sales_rep" or "prospect"
    timing_context: str  # How long into conversation, what happened before

class SalesExpertAgent:
    """
    Development-focused sales expert agent for coaching quality assurance
    """

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")

        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")

        # Expert system prompt
        self.expert_prompt = """You are a world-class sales trainer with 25+ years of experience training top performers at companies like Salesforce, HubSpot, Gong, and Outreach. You've personally trained thousands of sales reps and consistently helped them achieve 150%+ of quota.

Your expertise includes:
- SPIN Selling, Challenger Sale, Sandler, Gap Selling, Solution Selling methodologies
- Psychology of B2B buying behavior and decision-making
- Conversation timing, momentum, and flow management
- Industry-specific sales nuances (SaaS, Enterprise, SMB)
- What separates good sales reps from elite performers
- Advanced objection handling and closing techniques
- Building rapport and trust in sales conversations
- Mirroring techniques to encourage prospects to elaborate and share more details

Your job is to evaluate AI-generated coaching suggestions for real-time sales coaching. You must be brutally honest - mediocre coaching is worse than no coaching because it breaks conversation flow and damages rapport.

For each coaching suggestion, evaluate:
1. TIMING: Is this the right moment for this technique? (1-10)
2. TECHNIQUE: Is the suggested approach technically sound? (1-10)
3. EFFECTIVENESS: Would this actually help close the deal? (1-10)
4. RISK: Could this suggestion backfire or hurt the conversation?

Focus on what TOP PERFORMERS would actually do in this situation. Many coaching suggestions that sound good in theory fail in practice because they're:
- Poorly timed (interrupting natural flow)
- Too generic (not context-specific)
- Technically wrong (misunderstanding the methodology)
- Counterproductive (damaging rapport or momentum)

IMPORTANT: Mirroring is a powerful technique when prospects share pain points, challenges, or emotional statements. Reflecting back their exact words (like "Manual processes are frustrating?") encourages them to elaborate and share more details. This is especially effective early in discovery when you need prospects talking more than asking complex questions.

Be specific in your feedback and suggest better alternatives when the coaching is subpar."""

    async def evaluate_coaching(self, scenario: CoachingScenario) -> CoachingEvaluation:
        """
        Evaluate a coaching suggestion using sales expert knowledge
        """

        evaluation_prompt = f"""
SALES COACHING EVALUATION

CONTEXT:
- Call Goal: {scenario.call_goal}
- Conversation Phase: {scenario.conversation_phase}
- Timing Context: {scenario.timing_context}

CONVERSATION SNIPPET:
{scenario.transcript_snippet}
(Last speaker: {scenario.speaker})

OUR AI COACHING SUGGESTION:
"{scenario.our_suggestion}"

Please evaluate this coaching suggestion:

1. TIMING SCORE (1-10): Is this the right moment for this coaching?
2. TECHNIQUE SCORE (1-10): Is the suggested approach technically sound?
3. EFFECTIVENESS SCORE (1-10): Would this help the rep close more deals?
4. OVERALL SCORE (1-10): Overall quality of this coaching suggestion
5. TOP PERFORMER: Would an elite sales rep actually use this approach? (Yes/No)
6. RISK LEVEL: Low/Medium/High - could this suggestion backfire?

7. ISSUES: What's wrong with this suggestion? (if anything)
8. IMPROVEMENTS: How could this coaching be better?
9. BETTER APPROACH: What would you coach instead? (if applicable)
10. REASONING: Explain your evaluation in detail

Please respond in JSON format:
{{
    "timing_score": <1-10>,
    "technique_accuracy": <1-10>,
    "effectiveness_prediction": <1-10>,
    "overall_score": <1-10>,
    "would_top_performer_use": <true/false>,
    "risk_assessment": "<low/medium/high>",
    "issues": ["<issue1>", "<issue2>"],
    "improvements": ["<improvement1>", "<improvement2>"],
    "better_approach": "<alternative coaching suggestion or null>",
    "reasoning": "<detailed explanation>"
}}
"""

        try:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }

            payload = {
                "model": self.model,
                "max_tokens": 1500,
                "messages": [
                    {
                        "role": "user",
                        "content": f"{self.expert_prompt}\n\n{evaluation_prompt}"
                    }
                ],
                "temperature": 0.3  # Slightly creative but consistent
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload, timeout=30) as response:
                    if response.status == 200:
                        result = await response.json()
                        content = result.get("content", [{}])[0].get("text", "")

                        try:
                            # Clean content for JSON parsing (remove control characters)
                            cleaned_content = ''.join(char for char in content if ord(char) >= 32 or char in '\n\r\t')
                            # Parse JSON response
                            evaluation_data = json.loads(cleaned_content)

                            return CoachingEvaluation(
                                timing_score=evaluation_data.get("timing_score", 0),
                                technique_accuracy=evaluation_data.get("technique_accuracy", 0),
                                effectiveness_prediction=evaluation_data.get("effectiveness_prediction", 0),
                                overall_score=evaluation_data.get("overall_score", 0),
                                would_top_performer_use=evaluation_data.get("would_top_performer_use", False),
                                risk_assessment=evaluation_data.get("risk_assessment", "high"),
                                issues=evaluation_data.get("issues", []),
                                improvements=evaluation_data.get("improvements", []),
                                better_approach=evaluation_data.get("better_approach"),
                                reasoning=evaluation_data.get("reasoning", "")
                            )

                        except json.JSONDecodeError as e:
                            print(f"Failed to parse expert evaluation JSON: {e}")
                            print(f"Raw response: {content}")
                            # Return default low-quality evaluation
                            return CoachingEvaluation(
                                timing_score=1, technique_accuracy=1, effectiveness_prediction=1,
                                overall_score=1, would_top_performer_use=False, risk_assessment="high",
                                issues=["Failed to evaluate"], improvements=[], better_approach=None,
                                reasoning="Expert evaluation failed"
                            )
                    else:
                        print(f"Expert agent API error: {response.status}")
                        error_text = await response.text()
                        print(f"Error details: {error_text}")
                        return CoachingEvaluation(
                            timing_score=1, technique_accuracy=1, effectiveness_prediction=1,
                            overall_score=1, would_top_performer_use=False, risk_assessment="high",
                            issues=["API error"], improvements=[], better_approach=None,
                            reasoning="Expert evaluation API failed"
                        )

        except Exception as e:
            print(f"Expert agent error: {e}")
            return CoachingEvaluation(
                timing_score=1, technique_accuracy=1, effectiveness_prediction=1,
                overall_score=1, would_top_performer_use=False, risk_assessment="high",
                issues=[str(e)], improvements=[], better_approach=None,
                reasoning="Expert evaluation failed with exception"
            )

    def create_test_scenarios(self) -> List[CoachingScenario]:
        """
        Create test scenarios to validate our current coaching system
        """
        return [
            # Mirroring opportunity test
            CoachingScenario(
                conversation_context="Discovery call, 10 minutes in, good rapport established",
                transcript_snippet="Prospect: 'Our biggest challenge right now is that our manual processes are eating up so much time. It's really frustrating.'",
                our_suggestion="Mirror back: 'Manual processes are frustrating?' to get them talking more",
                call_goal="Discovery",
                conversation_phase="Problem exploration",
                speaker="prospect",
                timing_context="Prospect just shared a pain point, rep hasn't responded yet"
            ),

            # Objection handling test
            CoachingScenario(
                conversation_context="Demo call, shown features, discussing next steps",
                transcript_snippet="Prospect: 'This looks interesting, but I'm concerned about the price. It seems pretty expensive for what we're getting.'",
                our_suggestion="Price objection detected - don't defend price, ask: 'What were you hoping to invest?'",
                call_goal="Demo",
                conversation_phase="Objection handling",
                speaker="prospect",
                timing_context="After 20-minute demo, discussing implementation"
            ),

            # Talk ratio warning test
            CoachingScenario(
                conversation_context="Discovery call, rep has been explaining features",
                transcript_snippet="Sales Rep: '...and that's how our integration works with Salesforce, which I think would be really valuable for your team because it eliminates the manual data entry that you mentioned, and also provides real-time sync...'",
                our_suggestion="You've been talking for 2 minutes - ask a question to get them talking",
                call_goal="Discovery",
                conversation_phase="Discovery",
                speaker="sales_rep",
                timing_context="Rep has been speaking for 2+ minutes straight"
            ),

            # SPIN Selling test
            CoachingScenario(
                conversation_context="Discovery call, early stage, building understanding",
                transcript_snippet="Prospect: 'We use spreadsheets for everything - tracking leads, managing follow-ups, reporting to management.'",
                our_suggestion="They mentioned spreadsheets - ask how that affects other areas of their business",
                call_goal="Discovery",
                conversation_phase="Problem identification",
                speaker="prospect",
                timing_context="15 minutes into call, gathering situation information"
            ),

            # Closing opportunity test
            CoachingScenario(
                conversation_context="Follow-up call after demo, discussing implementation",
                transcript_snippet="Prospect: 'This could really solve our problems. What would implementation look like? How quickly could we get started?'",
                our_suggestion="Buying signals detected - ask for next steps",
                call_goal="Close",
                conversation_phase="Closing",
                speaker="prospect",
                timing_context="Strong interest expressed, asking about implementation"
            )
        ]

    async def run_quality_assessment(self):
        """
        Run a comprehensive quality assessment of our coaching system
        """
        print("Sales Expert Agent - Coaching Quality Assessment")
        print("="*60)

        test_scenarios = self.create_test_scenarios()
        total_score = 0
        evaluations = []

        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\nTest Scenario {i}: {scenario.conversation_phase}")
            print(f"Context: {scenario.timing_context}")
            print(f"Our Suggestion: '{scenario.our_suggestion}'")

            evaluation = await self.evaluate_coaching(scenario)
            evaluations.append(evaluation)
            total_score += evaluation.overall_score

            print(f"\nExpert Evaluation:")
            print(f"   Overall Score: {evaluation.overall_score}/10")
            print(f"   Timing: {evaluation.timing_score}/10 | Technique: {evaluation.technique_accuracy}/10 | Effectiveness: {evaluation.effectiveness_prediction}/10")
            print(f"   Top Performer Would Use: {'YES' if evaluation.would_top_performer_use else 'NO'}")
            print(f"   Risk Level: {evaluation.risk_assessment.upper()}")

            if evaluation.issues:
                print(f"   Issues: {', '.join(evaluation.issues)}")

            if evaluation.better_approach:
                print(f"   Better Approach: '{evaluation.better_approach}'")

            print(f"   Reasoning: {evaluation.reasoning}")

        print(f"\nOVERALL ASSESSMENT")
        print(f"="*40)
        average_score = total_score / len(test_scenarios)
        print(f"Average Coaching Quality: {average_score:.1f}/10")

        high_quality = sum(1 for e in evaluations if e.overall_score >= 8)
        acceptable = sum(1 for e in evaluations if 6 <= e.overall_score < 8)
        needs_improvement = sum(1 for e in evaluations if e.overall_score < 6)

        print(f"High Quality (8+): {high_quality}/{len(test_scenarios)}")
        print(f"Acceptable (6-7): {acceptable}/{len(test_scenarios)}")
        print(f"Needs Improvement (<6): {needs_improvement}/{len(test_scenarios)}")

        if average_score >= 8:
            print("Excellent! Your coaching system is ready for testing.")
        elif average_score >= 6:
            print("Good foundation, but some coaching needs refinement.")
        else:
            print("Coaching system needs significant improvement before deployment.")

        return evaluations

# Development testing function
async def main():
    """
    Run the sales expert agent quality assessment
    """
    expert = SalesExpertAgent()
    await expert.run_quality_assessment()

if __name__ == "__main__":
    asyncio.run(main())