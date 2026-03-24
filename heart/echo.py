"""
heart/echo.py — ECHO, the Tracking Agent.

ECHO is the observational intelligence of the system.
It hooks into every agent invocation and scores the output
across 5 dimensions using Claude as the judge.

ECHO's scores are the fuel that DARWIN uses to evolve agents.
Without ECHO, there is no feedback loop.
Without feedback, there is no growth.

ECHO never blocks execution — it runs asynchronously after
each agent completes, so the build pipeline is never slowed.
"""

from __future__ import annotations
import uuid
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import openai

from state import EchoReport, AgentState
from heart.memoria import Memoria
import config


# ─────────────────────────────────────────────────────────────────────────────
#  ECHO Scoring Prompt
# ─────────────────────────────────────────────────────────────────────────────

ECHO_SYSTEM_PROMPT = """You are ECHO, an objective AI performance evaluator.
Your role is to score the output of a specialized AI agent on 5 dimensions.
Be rigorous, fair, and specific. Do not inflate scores.
A score of 10 means world-class, production-ready perfection.
A score of 5 means acceptable but with significant gaps.
A score below 3 means the output failed its core purpose.

Always respond in valid JSON only. No markdown, no preamble.
"""

ECHO_SCORING_TEMPLATE = """Evaluate this agent output:

AGENT: {agent_id}
AGENT ROLE: {agent_role}
INPUT CONTRACT (what was given to this agent):
{input_summary}

AGENT OUTPUT:
{output_summary}

Score on these 5 dimensions (0.0 to 10.0 each):
1. quality — Is the output technically correct and production-worthy?
2. completeness — Did it cover everything required by the input contract?
3. contract_adherence — Did it strictly follow the format/structure expected?
4. efficiency — Is it lean, non-redundant, and well-structured?
5. innovation — Did it exceed the minimum and bring creative value?

Also provide:
- assessment: 2-3 sentence evaluation of the output
- improvement_suggestions: array of 2-4 specific, actionable improvements

Respond ONLY in this exact JSON format:
{{
  "score_quality": 0.0,
  "score_completeness": 0.0,
  "score_contract_adherence": 0.0,
  "score_efficiency": 0.0,
  "score_innovation": 0.0,
  "assessment": "...",
  "improvement_suggestions": ["...", "..."]
}}"""


# ─────────────────────────────────────────────────────────────────────────────
#  Agent Role Descriptions (for ECHO context)
# ─────────────────────────────────────────────────────────────────────────────

AGENT_ROLES = {
    "NEXUS":  "Orchestrator that decomposes human intent into an execution plan",
    "PRISM":  "Product strategist that converts ideas into PRDs and user stories",
    "ATLAS":  "System architect that designs tech stack, API contracts, and schemas",
    "PIXEL":  "Frontend engineer that builds UI components and pages",
    "FORGE":  "Backend engineer that builds APIs, auth, and integrations",
    "VAULT":  "Database architect that designs schemas, migrations, and indexes",
    "CIPHER": "Security engineer that audits code and hardens the system",
    "WEAVE":  "AI/ML engineer that builds LLM features, RAG pipelines, and prompts",
    "PROBE":  "QA engineer that writes and runs tests to find bugs",
    "LENS":   "Code reviewer that enforces quality standards and architecture",
    "LAUNCH": "DevOps engineer that containerizes and deploys the product",
    "SIGNAL": "Observability engineer that sets up logging, metrics, and alerts",
    "INK":    "Technical writer that documents the product for users and developers",
}


# ─────────────────────────────────────────────────────────────────────────────
#  ECHO Agent
# ─────────────────────────────────────────────────────────────────────────────

class Echo:
    """
    ECHO — Tracks and scores every agent execution.
    Uses Claude as the judge to produce dimensional scores.
    Saves all reports to MEMORIA for DARWIN to analyze.
    """

    def __init__(self, memoria: Memoria):
        self.memoria = memoria
        self.client = openai.AsyncOpenAI(
            api_key=config.KIMI_API_KEY,
            base_url=config.KIMI_BASE_URL,
        )
        self.model = config.AGENT_MODELS["ECHO"]
        self.temperature = config.AGENT_TEMPERATURES["ECHO"]

    async def score(
        self,
        agent_id: str,
        project_id: str,
        genome_version: int,
        input_summary: str,
        output_summary: str,
        duration_ms: int,
    ) -> EchoReport:
        """
        Score an agent's output. This is the core ECHO function.
        Returns an EchoReport with dimensional scores and analysis.
        """
        tier = config.AGENT_TIERS.get(agent_id, "T2")
        weights = config.ECHO_SCORING["tier_weights"][tier]
        agent_role = AGENT_ROLES.get(agent_id, "Specialized AI agent")

        prompt = ECHO_SCORING_TEMPLATE.format(
            agent_id=agent_id,
            agent_role=agent_role,
            input_summary=input_summary[:2000],   # Truncate for context limits
            output_summary=output_summary[:3000],
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=1500,
                temperature=1.0,
                messages=[
                    {"role": "system", "content": "You are a scoring engine. Respond ONLY with valid JSON. No explanation."},
                    {"role": "user", "content": prompt}
                ]
            )

            content = response.choices[0].message.content or ""
            reasoning = response.choices[0].message.reasoning_content or ""
            import re

            raw = None
            parsed_scores = None

            # Strategy 1: look for clean JSON in content
            if content.strip():
                for block in reversed(re.findall(r'\{[\s\S]*?\}', content)):
                    try:
                        test = json.loads(block)
                        if "score_quality" in test:
                            raw = block
                            parsed_scores = test
                            break
                    except json.JSONDecodeError:
                        continue

            # Strategy 2: parse score values from text (reasoning or content)
            if not parsed_scores:
                text = reasoning or content
                parsed_scores = {}
                found = False
                for field in ["score_quality", "score_completeness", "score_contract_adherence",
                              "score_efficiency", "score_innovation"]:
                    m = re.search(rf'"{field}"\s*:\s*([0-9.]+)', text)
                    if m:
                        parsed_scores[field] = float(m.group(1))
                        found = True
                if found:
                    parsed_scores.setdefault("assessment", "")
                    parsed_scores.setdefault("improvement_suggestions", [])

            if not parsed_scores or not any(k in parsed_scores for k in ["score_quality"]):
                raise ValueError(f"No score fields found. content={content[:100]}, reasoning={reasoning[:100]}")

        except Exception as e:
            # Fallback — neutral scores, don't break pipeline
            print(f"[ECHO] Scoring failed for {agent_id}: {e}. Using neutral scores.")
            parsed_scores = {
                "score_quality": 5.0,
                "score_completeness": 5.0,
                "score_contract_adherence": 5.0,
                "score_efficiency": 5.0,
                "score_innovation": 5.0,
                "assessment": "ECHO scoring failed — neutral scores applied.",
                "improvement_suggestions": [],
            }

        # Compute weighted composite score
        composite = (
            parsed_scores["score_quality"]            * weights["quality"] +
            parsed_scores["score_completeness"]       * weights["completeness"] +
            parsed_scores["score_contract_adherence"] * weights["contract_adherence"] +
            parsed_scores["score_efficiency"]         * weights["efficiency"] +
            parsed_scores["score_innovation"]         * weights["innovation"]
        )

        report = EchoReport(
            run_id=str(uuid.uuid4()),
            agent_id=agent_id,
            genome_version=genome_version,
            project_id=project_id,
            score_quality=parsed_scores["score_quality"],
            score_completeness=parsed_scores["score_completeness"],
            score_contract_adherence=parsed_scores["score_contract_adherence"],
            score_efficiency=parsed_scores["score_efficiency"],
            score_innovation=parsed_scores["score_innovation"],
            composite_score=round(composite, 2),
            assessment=parsed_scores.get("assessment", ""),
            improvement_suggestions=parsed_scores.get("improvement_suggestions", []),
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Persist to MEMORIA
        await self.memoria.save_echo_report(report)

        # Update genome fitness score in MEMORIA
        await self._update_genome_fitness(agent_id, genome_version, composite)

        return report

    async def _update_genome_fitness(
        self,
        agent_id: str,
        genome_version: int,
        new_score: float
    ):
        """Update the rolling fitness score for the active genome."""
        current_fitness = await self.memoria.get_agent_fitness(agent_id)
        # Exponential moving average — new data has more weight
        updated_fitness = (current_fitness * 0.7) + (new_score * 0.3)

        # Get current genome and update its fitness
        genome = await self.memoria.get_active_genome(agent_id)
        if genome:
            genome["fitness_score"] = round(updated_fitness, 3)
            await self.memoria.save_genome(genome)

    def format_input_summary(self, state: AgentState, agent_id: str) -> str:
        """Extract a concise input summary from state for a specific agent."""
        parts = [f"Human Intent: {state.get('human_intent', 'N/A')}"]

        if agent_id == "PRISM":
            parts.append("Input: Raw human intent only")
        elif agent_id == "ATLAS":
            parts.append(f"PRD from PRISM:\n{state.get('prd', 'N/A')[:500]}")
        elif agent_id in ("PIXEL", "FORGE"):
            parts.append(f"Architecture: {state.get('architecture', 'N/A')[:300]}")
            parts.append(f"API Contract: {state.get('api_contract', 'N/A')[:300]}")
        elif agent_id == "VAULT":
            parts.append(f"Data Schema from ATLAS: {state.get('data_schema', 'N/A')[:300]}")
        elif agent_id == "CIPHER":
            parts.append(f"Backend Code length: {len(state.get('backend_code', '') or '')}")
            parts.append(f"Frontend Code length: {len(state.get('frontend_code', '') or '')}")
        elif agent_id in ("PROBE", "LENS"):
            parts.append(f"Full codebase available. Backend len: {len(state.get('backend_code', '') or '')}")
        elif agent_id == "LAUNCH":
            parts.append(f"Quality gate passed: {state.get('quality_gate_passed', False)}")
        elif agent_id in ("SIGNAL", "INK"):
            parts.append(f"Deployment config available: {bool(state.get('deployment_config'))}")

        return "\n".join(parts)
