"""
state.py — Shared state schema for the Agent Command LangGraph system.
This is the single source of truth that flows through every node.
"""

from __future__ import annotations
from typing import TypedDict, Annotated, List, Optional, Dict, Any
import operator
from langgraph.graph.message import add_messages


# ─────────────────────────────────────────────
#  Agent Genome — The DNA of an agent
# ─────────────────────────────────────────────
class AgentGenome(TypedDict):
    """The evolving configuration of an agent. Darwin mutates this over time."""
    agent_id: str
    system_prompt: str          # The core instructions that define this agent
    model: str                  # Which model to use
    temperature: float          # Sampling temperature
    version: int                # Genome version (increments with each evolution)
    generation: int             # Darwin generation (increments with full team evolution)
    fitness_score: float        # Rolling average score (0-10)
    created_at: str
    parent_version: Optional[int]   # Which genome this was evolved from
    mutation_notes: Optional[str]   # Why Darwin changed this genome


# ─────────────────────────────────────────────
#  Echo Report — What ECHO produces per agent run
# ─────────────────────────────────────────────
class EchoReport(TypedDict):
    """Scoring report produced by ECHO for a single agent invocation."""
    run_id: str
    agent_id: str
    genome_version: int
    project_id: str
    # Raw dimension scores (0-10 each)
    score_quality: float
    score_completeness: float
    score_contract_adherence: float
    score_efficiency: float
    score_innovation: float
    # Weighted composite
    composite_score: float
    # ECHO's rationale
    assessment: str
    # Suggestions for improvement
    improvement_suggestions: List[str]
    duration_ms: int
    timestamp: str


# ─────────────────────────────────────────────
#  Evolution Record — What DARWIN produces
# ─────────────────────────────────────────────
class EvolutionRecord(TypedDict):
    """A genome mutation event produced by DARWIN."""
    evolution_id: str
    agent_id: str
    from_version: int
    to_version: int
    trigger: str                    # why evolution was triggered
    weak_dimensions: List[str]      # which dimensions were underperforming
    fitness_before: float
    fitness_after: Optional[float]  # filled in after new genome is tested
    prompt_diff_summary: str        # human-readable summary of changes
    accepted: bool                  # did new genome beat old one?
    timestamp: str


# ─────────────────────────────────────────────
#  Build Phase
# ─────────────────────────────────────────────
class BuildPhase(TypedDict):
    phase_num: int
    name: str
    status: str     # pending | running | complete | failed
    agents: List[str]
    outputs: Dict[str, str]
    started_at: Optional[str]
    completed_at: Optional[str]


# ─────────────────────────────────────────────
#  Main Graph State — flows through all nodes
# ─────────────────────────────────────────────
class AgentState(TypedDict):
    # ── Conversation ──────────────────────────
    messages: Annotated[list, add_messages]

    # ── Project Identity ──────────────────────
    project_id: str
    human_intent: str           # The raw human request
    nexus_plan: Optional[str]   # NEXUS decomposed execution plan

    # ── Phase Tracking ────────────────────────
    current_phase: Annotated[int, operator.add]  # last-writer-wins via add
    quality_gate_passed: bool
    quality_retry_count: int
    phases: Dict[str, BuildPhase]

    # ── Tier 1 Outputs (Strategy) ─────────────
    prd: Optional[str]                  # PRISM
    architecture: Optional[str]         # ATLAS
    api_contract: Optional[str]         # ATLAS
    data_schema: Optional[str]          # ATLAS

    # ── Tier 2 Outputs (Build) ────────────────
    frontend_code: Optional[str]        # PIXEL
    backend_code: Optional[str]         # FORGE
    database_migrations: Optional[str]  # VAULT
    security_audit: Optional[str]       # CIPHER
    ai_modules: Optional[str]           # WEAVE (optional)
    needs_ai_features: bool

    # ── Tier 3 Outputs (Quality) ──────────────
    test_suite: Optional[str]           # PROBE
    probe_score: float                  # PROBE composite score
    review_report: Optional[str]        # LENS
    lens_score: float                   # LENS composite score

    # ── Tier 4 Outputs (Ship) ─────────────────
    deployment_config: Optional[str]    # LAUNCH
    observability_config: Optional[str] # SIGNAL
    documentation: Optional[str]        # INK

    # ── Heart: ECHO Tracking ──────────────────
    echo_reports: Annotated[List[EchoReport], operator.add]
    run_id: str

    # ── Heart: DARWIN Evolution ───────────────
    evolution_records: Annotated[List[EvolutionRecord], operator.add]
    darwin_triggered: bool

    # ── Final Output ──────────────────────────
    final_report: Optional[str]
    error: Optional[str]
