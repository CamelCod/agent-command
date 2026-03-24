"""
heart/darwin.py — DARWIN, the Evolution Engine.

DARWIN is the self-improvement intelligence of the system.
It reads ECHO's accumulated performance data, identifies which agents
are underperforming, and uses Claude to generate improved system prompts.

Evolution cycle:
  1. Check if any agent has hit the run threshold
  2. Compute fitness and identify weak dimensions
  3. Call Claude with the old prompt + weak dimension data
  4. Claude generates a mutated prompt addressing the weaknesses
  5. Save new genome to MEMORIA
  6. Flag the evolution event for future A/B comparison

This gives the team a form of natural selection —
agents that perform well keep their prompts,
agents that struggle have their prompts rewritten.

"It is not the strongest of the species that survives,
 nor the most intelligent. It is the one most responsive to change."
"""

from __future__ import annotations
import uuid
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import openai

from state import AgentGenome, EvolutionRecord
from heart.memoria import Memoria
import config


# ─────────────────────────────────────────────────────────────────────────────
#  DARWIN System Prompt
# ─────────────────────────────────────────────────────────────────────────────

DARWIN_SYSTEM_PROMPT = """You are DARWIN, an AI prompt evolution specialist.
Your job is to improve the system prompts of specialized AI coding and product agents.
You receive an agent's current system prompt and its performance weaknesses,
then produce an improved system prompt that addresses those specific weaknesses.

Rules:
- Preserve all core responsibilities and capabilities of the agent
- Make targeted improvements — don't rewrite things that are working well
- Address the weak dimensions directly with concrete instructions
- Keep the improved prompt clear, directive, and implementable
- The improved prompt should be a complete replacement (not a diff)
- Include specific examples or patterns where they help
- Respond ONLY in valid JSON. No markdown, no preamble.
"""

DARWIN_EVOLUTION_TEMPLATE = """Agent to evolve: {agent_id}
Agent role: {agent_role}
Current genome version: {current_version}
Generation: {generation}

PERFORMANCE DATA (last {last_n} runs):
Overall fitness score: {fitness:.2f}/10.0
Threshold for evolution: {threshold}/10.0

Dimension breakdown:
{dimension_breakdown}

WEAKEST DIMENSIONS (need improvement):
{weak_dims_str}

ECHO's recurring suggestions from recent runs:
{echo_suggestions}

CURRENT SYSTEM PROMPT:
{current_prompt}

EVOLUTION HISTORY (what has been tried before):
{evolution_history}

Generate an improved system prompt that:
1. Directly addresses the weak dimensions listed above
2. Incorporates the specific suggestions from ECHO
3. Builds on what's working in the current prompt
4. Avoids repeating mutations from evolution history that didn't work

Respond in this exact JSON format:
{{
  "improved_prompt": "...",
  "mutation_notes": "Brief description of what changed and why (2-3 sentences)",
  "targeted_dimensions": ["dimension1", "dimension2"],
  "confidence": 0.0
}}"""


# ─────────────────────────────────────────────────────────────────────────────
#  DARWIN Agent Role Descriptions (more detailed than ECHO)
# ─────────────────────────────────────────────────────────────────────────────

DARWIN_AGENT_ROLES = {
    "NEXUS":  "Meta-orchestrator that decomposes human intent into multi-agent execution plans using dependency graphs",
    "PRISM":  "Product strategist specializing in converting vague ideas into precise PRDs, user stories, acceptance criteria, and MVP scoping",
    "ATLAS":  "System architect who designs complete tech stacks, API contracts (OpenAPI), database schemas (ERD), and scalability architectures",
    "PIXEL":  "Frontend engineer building production React/Next.js components, state management, routing, and API integration",
    "FORGE":  "Backend engineer building Node.js/Python APIs, authentication systems, background jobs, and third-party integrations",
    "VAULT":  "Database architect designing optimal schemas, writing migration files, indexing strategies, and caching layers",
    "CIPHER": "Security engineer performing OWASP Top 10 audits, hardening auth, implementing rate limiting, and managing secrets",
    "WEAVE":  "AI/ML engineer building RAG pipelines, LLM integrations, prompt systems, vector stores, and AI feature modules",
    "PROBE":  "QA engineer writing comprehensive test suites (unit, integration, E2E), finding edge cases, and producing coverage reports",
    "LENS":   "Senior code reviewer enforcing architecture standards, identifying technical debt, and optimizing performance",
    "LAUNCH": "DevOps engineer writing Dockerfiles, CI/CD pipelines, Terraform configs, and executing zero-downtime deployments",
    "SIGNAL": "Observability engineer instrumenting apps with logging, Prometheus metrics, Grafana dashboards, and alert rules",
    "INK":    "Technical writer creating READMEs, API docs, user guides, changelogs, and runbooks from code artifacts",
}


# ─────────────────────────────────────────────────────────────────────────────
#  DARWIN Class
# ─────────────────────────────────────────────────────────────────────────────

class Darwin:
    """
    DARWIN — The evolution engine for the agent team.
    Analyzes ECHO data and generates improved agent prompts.
    """

    def __init__(self, memoria: Memoria):
        self.memoria = memoria
        self.client = openai.AsyncOpenAI(
            api_key=config.KIMI_API_KEY,
            base_url=config.KIMI_BASE_URL,
        )
        self.model = config.AGENT_MODELS["DARWIN"]
        self.temperature = config.AGENT_TEMPERATURES["DARWIN"]
        self.evo_config = config.EVOLUTION_CONFIG

    async def check_and_evolve(self, agent_id: str) -> Optional[EvolutionRecord]:
        """
        Check if an agent needs evolution. If so, run the evolution cycle.
        Returns an EvolutionRecord if evolution occurred, None otherwise.
        """
        run_count = await self.memoria.get_run_count(agent_id)

        # Only trigger evolution after enough data
        if run_count < self.evo_config["runs_before_evolution"]:
            return None

        # Only evolve if it's a checkpoint run (every N runs)
        if run_count % self.evo_config["runs_before_evolution"] != 0:
            return None

        fitness = await self.memoria.get_agent_fitness(agent_id)

        # Only evolve if fitness is below threshold
        if fitness >= self.evo_config["fitness_threshold"]:
            return None

        print(f"[DARWIN] Evolution triggered for {agent_id} — fitness {fitness:.2f} < {self.evo_config['fitness_threshold']}")
        return await self._evolve(agent_id, fitness)

    async def force_evolve(self, agent_id: str) -> Optional[EvolutionRecord]:
        """Force an evolution cycle regardless of fitness score."""
        fitness = await self.memoria.get_agent_fitness(agent_id)
        return await self._evolve(agent_id, fitness, forced=True)

    async def evolve_team(self) -> List[EvolutionRecord]:
        """Run the evolution check on every agent in the team."""
        records = []
        for agent_id in config.AGENT_TIERS.keys():
            record = await self.check_and_evolve(agent_id)
            if record:
                records.append(record)
        return records

    async def evolve_agents(self, agent_ids: List[str]) -> List[EvolutionRecord]:
        # -------------------------------------------------------
        # FUNCTION: evolve_agents
        # GOAL:     Run targeted DARWIN evolution on a specific list of agents.
        # INPUT:    agent_ids (List[str]) — agent IDs to evolve
        # OUTPUT:   Returns List[EvolutionRecord] for evolved agents.
        # STEPS:
        #   1. Validate each agent_id against known agent tiers.
        #   2. Call _evolve() for each valid agent.
        #   3. Collect and return all evolution records.
        # -------------------------------------------------------
        records = []
        for agent_id in agent_ids:
            if agent_id not in config.AGENT_TIERS:
                print(f"[DARWIN] Unknown agent: {agent_id}. Skipping.")
                continue
            record = await self.check_and_evolve(agent_id)
            if record:
                records.append(record)
        return records

    async def _evolve(
        self,
        agent_id: str,
        fitness: float,
        forced: bool = False
    ) -> Optional[EvolutionRecord]:
        """Core evolution logic — generates a new genome via prompt mutation."""

        # Get current genome
        current_genome = await self.memoria.get_active_genome(agent_id)
        if not current_genome:
            print(f"[DARWIN] No genome found for {agent_id}. Skipping evolution.")
            return None

        # Get weakness data
        dimension_scores = await self.memoria.get_weak_dimensions(agent_id)
        weak_dims = sorted(
            dimension_scores.items(),
            key=lambda x: x[1]
        )[:3]  # Top 3 weakest

        # Get recent ECHO suggestions
        recent_reports = await self.memoria.get_recent_reports(agent_id, limit=10)
        all_suggestions = []
        for report in recent_reports:
            all_suggestions.extend(report["improvement_suggestions"])
        # Deduplicate and take top suggestions
        unique_suggestions = list(dict.fromkeys(all_suggestions))[:8]

        # Get evolution history (to avoid repeating failed mutations)
        evo_history = await self.memoria.get_evolution_history(agent_id)
        evo_summary = "\n".join([
            f"v{r['from_version']}→v{r['to_version']}: {r['prompt_diff_summary']} "
            f"({'accepted' if r['accepted'] else 'rejected'})"
            for r in evo_history[-3:]  # Last 3 evolutions
        ]) or "No evolution history yet"

        # Format dimension breakdown
        dim_breakdown = "\n".join([
            f"  {dim}: {score:.2f}/10.0 {'⚠️ WEAK' if score < 6.0 else '✓'}"
            for dim, score in dimension_scores.items()
        ])

        weak_dims_str = "\n".join([
            f"  - {dim}: {score:.2f}/10.0 (needs improvement)"
            for dim, score in weak_dims
        ])

        # Build the evolution prompt
        prompt = DARWIN_EVOLUTION_TEMPLATE.format(
            agent_id=agent_id,
            agent_role=DARWIN_AGENT_ROLES.get(agent_id, "Specialized AI agent"),
            current_version=current_genome["version"],
            generation=current_genome["generation"],
            last_n=10,
            fitness=fitness,
            threshold=self.evo_config["fitness_threshold"],
            dimension_breakdown=dim_breakdown,
            weak_dims_str=weak_dims_str,
            echo_suggestions="\n".join(f"  - {s}" for s in unique_suggestions),
            current_prompt=current_genome["system_prompt"],
            evolution_history=evo_summary,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=3000,
                temperature=1.0,  # Kimi kimi-k2.5 requires exactly 1.0
                messages=[
                    {"role": "system", "content": DARWIN_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )

            raw = (response.choices[0].message.content or response.choices[0].message.reasoning_content or "").strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            mutation = json.loads(raw)

        except Exception as e:
            print(f"[DARWIN] Evolution failed for {agent_id}: {e}")
            return None

        # Create the new genome
        new_version = current_genome["version"] + 1
        new_genome = AgentGenome(
            agent_id=agent_id,
            system_prompt=mutation["improved_prompt"],
            model=current_genome["model"],
            temperature=current_genome["temperature"],
            version=new_version,
            generation=current_genome["generation"] + 1,
            fitness_score=fitness,  # Will be updated by ECHO as it runs
            created_at=datetime.now(timezone.utc).isoformat(),
            parent_version=current_genome["version"],
            mutation_notes=mutation.get("mutation_notes", ""),
        )

        # Save to MEMORIA
        await self.memoria.save_genome(new_genome)

        # Create evolution record
        trigger = f"forced_evolution" if forced else f"fitness_below_threshold_{fitness:.2f}"
        record = EvolutionRecord(
            evolution_id=str(uuid.uuid4()),
            agent_id=agent_id,
            from_version=current_genome["version"],
            to_version=new_version,
            trigger=trigger,
            weak_dimensions=[d for d, _ in weak_dims],
            fitness_before=fitness,
            fitness_after=None,    # Filled in after new genome is tested
            prompt_diff_summary=mutation.get("mutation_notes", ""),
            accepted=True,         # Optimistic — will revert if worse
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        await self.memoria.save_evolution_record(record)

        print(f"[DARWIN] ✓ Evolved {agent_id} v{current_genome['version']} → v{new_version}")
        print(f"[DARWIN]   Focus: {', '.join([d for d, _ in weak_dims])}")
        print(f"[DARWIN]   Notes: {mutation.get('mutation_notes', '')[:100]}")

        return record

    async def get_evolution_report(self) -> str:
        """Generate a human-readable evolution report for all agents."""
        health = await self.memoria.get_team_health()

        lines = [
            "═══════════════════════════════════════",
            "       DARWIN TEAM EVOLUTION REPORT    ",
            "═══════════════════════════════════════",
        ]

        for agent_id, data in sorted(health.items(), key=lambda x: x[1]["fitness"]):
            tier = config.AGENT_TIERS.get(agent_id, "??")
            fitness_bar = "█" * int(data["fitness"]) + "░" * (10 - int(data["fitness"]))
            lines.append(
                f"{agent_id:8} [{tier}] "
                f"fitness: [{fitness_bar}] {data['fitness']:.1f} | "
                f"runs: {data['runs']:3d} | "
                f"genome: v{data['genome_version']} gen{data['generation']}"
            )

        lines.append("═══════════════════════════════════════")
        return "\n".join(lines)
