"""
graph.py — The main LangGraph pipeline for Agent Command.

This file wires all 13 agents + ECHO + DARWIN into a
single StateGraph with 4 build phases.

Flow:
  START → nexus → prism → atlas
        → [parallel] pixel, forge, vault, cipher, [weave?]
        → [parallel] probe, lens → quality_gate
        → [if pass] launch → signal → ink → darwin_check → END
        → [if fail] retry or escalate → END

The graph is the skeleton.
The genomes are the soul.
ECHO is the eyes.
DARWIN is the evolution.
"""

from __future__ import annotations
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Literal

from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages

from state import AgentState
from agents.team import (
    Nexus, Prism, Atlas,
    Pixel, Forge, Vault, Cipher, Weave,
    Probe, Lens,
    Launch, Signal, Ink,
)
from heart.memoria import Memoria
from heart.echo import Echo
from heart.darwin import Darwin
from heart.analytics import PipelineAnalytics
import config


# ─────────────────────────────────────────────────────────────────────────────
#  Graph Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_graph(memoria: Memoria, echo: Echo, darwin: Darwin, analytics: PipelineAnalytics | None = None) -> StateGraph:
    """
    Assemble and compile the full Agent Command LangGraph.
    Returns a compiled, runnable graph.
    """

    # ── Instantiate all agents ───────────────────────────────────────────────
    nexus  = Nexus(memoria, echo)
    prism  = Prism(memoria, echo)
    atlas  = Atlas(memoria, echo)
    pixel  = Pixel(memoria, echo)
    forge  = Forge(memoria, echo)
    vault  = Vault(memoria, echo)
    cipher = Cipher(memoria, echo)
    weave  = Weave(memoria, echo)
    probe  = Probe(memoria, echo)
    lens   = Lens(memoria, echo)
    launch = Launch(memoria, echo)
    signal = Signal(memoria, echo)
    ink    = Ink(memoria, echo)

    # ── Graph ────────────────────────────────────────────────────────────────
    graph = StateGraph(AgentState)

    # ── Phase 1: Strategy (sequential) ──────────────────────────────────────
    graph.add_node("nexus",  nexus.invoke)
    graph.add_node("prism",  prism.invoke)
    graph.add_node("atlas",  atlas.invoke)

    # ── Phase 2: Build (parallel fan-out via aggregation) ───────────────────
    graph.add_node("pixel",  pixel.invoke)
    graph.add_node("forge",  forge.invoke)
    graph.add_node("vault",  vault.invoke)
    graph.add_node("cipher", cipher.invoke)
    graph.add_node("weave",  weave.invoke)
    graph.add_node("build_sync",  _make_build_sync(analytics))   # Fan-in after parallel build

    # ── Phase 3: Quality Gate (parallel) ────────────────────────────────────
    graph.add_node("probe",  probe.invoke)
    graph.add_node("lens",   lens.invoke)
    graph.add_node("quality_gate", _make_quality_gate(analytics))

    # ── Phase 4: Ship ────────────────────────────────────────────────────────
    graph.add_node("launch", launch.invoke)
    graph.add_node("signal", signal.invoke)
    graph.add_node("ink",    ink.invoke)

    # ── Heart: Darwin Evolution ───────────────────────────────────────────────
    graph.add_node("darwin_check", _make_darwin_check(darwin, analytics))

    # ── Final Report ─────────────────────────────────────────────────────────
    from functools import partial
    graph.add_node("finalize", partial(_finalize, analytics=analytics))

    # ─────────────────────────────────────────────────────────────────────────
    #  EDGES — the flow of the pipeline
    # ─────────────────────────────────────────────────────────────────────────

    # Phase 1: Sequential strategy chain
    graph.add_edge(START, "nexus")
    graph.add_edge("nexus", "prism")
    graph.add_edge("prism", "atlas")

    # Phase 2: Atlas fans out to all build agents
    # We route through a dispatcher node to run them "in parallel"
    # (LangGraph executes them as sequential nodes — true async parallel
    #  requires Send API which we implement via fan-out pattern)
    graph.add_node("build_dispatch", _make_build_dispatch(analytics))
    graph.add_edge("atlas", "build_dispatch")

    # Build dispatch fans to all build agents
    graph.add_edge("build_dispatch", "pixel")
    graph.add_edge("build_dispatch", "forge")
    graph.add_edge("build_dispatch", "vault")
    graph.add_edge("build_dispatch", "cipher")

    # WEAVE is conditional — only if AI features needed
    graph.add_conditional_edges(
        "build_dispatch",
        _needs_ai,
        {"yes": "weave", "no": "build_sync"}
    )

    # Build agents fan-in to sync node
    graph.add_edge("pixel",  "build_sync")
    graph.add_edge("forge",  "build_sync")
    graph.add_edge("vault",  "build_sync")
    graph.add_edge("cipher", "build_sync")
    graph.add_edge("weave",  "build_sync")

    # Phase 3: Quality — both run, then gate
    graph.add_edge("build_sync", "probe")
    graph.add_edge("build_sync", "lens")
    graph.add_edge("probe", "quality_gate")
    graph.add_edge("lens",  "quality_gate")

    # Quality gate: pass goes to Phase 4, fail loops back or escalates
    graph.add_conditional_edges(
        "quality_gate",
        _gate_decision,
        {
            "pass":    "launch",
            "retry":   "forge",    # Loop back to rebuild with fix notes
            "escalate": "finalize", # Too many retries — escalate to human
        }
    )

    # Phase 4: Ship
    graph.add_edge("launch", "signal")
    graph.add_edge("signal", "ink")
    graph.add_edge("ink",    "darwin_check")
    graph.add_edge("darwin_check", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
#  Node Functions (non-agent logic nodes)
# ─────────────────────────────────────────────────────────────────────────────

async def _build_dispatch(state: AgentState) -> Dict[str, Any]:
    """Fan-out marker — transitions state to build phase."""
    print("\n[PIPELINE] ═══ PHASE 2: BUILD (parallel) ═══")
    return {"current_phase": 2}


async def _build_sync(state: AgentState) -> Dict[str, Any]:
    """Fan-in sync — waits for all build agents to complete."""
    print("[PIPELINE] ═══ Build phase complete — syncing outputs ═══")
    return {"current_phase": 2}


async def _quality_gate(state: AgentState) -> Dict[str, Any]:
    """Evaluate QA + review scores against thresholds using actual ECHO composite scores."""
    echo_reports = state.get("echo_reports", [])

    # Get the most recent ECHO report for PROBE and LENS
    probe_reports = [r for r in echo_reports if r.get("agent_id") == "PROBE"]
    lens_reports  = [r for r in echo_reports if r.get("agent_id") == "LENS"]

    probe_score = probe_reports[-1]["composite_score"] if probe_reports else 0.0
    lens_score  = lens_reports[-1]["composite_score"]  if lens_reports  else 0.0

    retry_count = state.get("quality_retry_count", 0)

    passed = (
        probe_score >= config.QUALITY_GATE["min_probe_score"] and
        lens_score  >= config.QUALITY_GATE["min_lens_score"]
    )

    if passed:
        print(f"[QUALITY GATE] ✅ PASS — probe: {probe_score:.1f}, lens: {lens_score:.1f}")
    else:
        print(f"[QUALITY GATE] ❌ FAIL — probe: {probe_score:.1f}, lens: {lens_score:.1f}")

    return {
        "quality_gate_passed": passed,
        "quality_retry_count": retry_count + (0 if passed else 1),
        "current_phase": 3,
    }


def _gate_decision(state: AgentState) -> Literal["pass", "retry", "escalate"]:
    """Conditional edge: determine what happens after the quality gate."""
    if state.get("quality_gate_passed"):
        return "pass"
    if state.get("quality_retry_count", 0) >= config.QUALITY_GATE["max_retries"]:
        print("[QUALITY GATE] ⚠️  Max retries reached — escalating to human")
        return "escalate"
    print(f"[QUALITY GATE] 🔄 Retry #{state.get('quality_retry_count', 1)}")
    return "retry"


def _needs_ai(state: AgentState) -> Literal["yes", "no"]:
    """Conditional edge: does this build need WEAVE?"""
    return "yes" if state.get("needs_ai_features", False) else "no"


def _make_darwin_check(darwin: Darwin, analytics: PipelineAnalytics | None):
    """Factory that closes over the darwin instance."""
    async def _darwin_check(state: AgentState) -> Dict[str, Any]:
        """Post-ship: run Darwin evolution check for any agent that needs it."""
        print("\n[DARWIN] Checking team for evolution opportunities...")
        records = await darwin.evolve_team()

        if records:
            print(f"[DARWIN] Evolved {len(records)} agent(s) this cycle")
            if analytics:
                for r in records:
                    await analytics.emit_evolution(
                        agent_id=r["agent_id"],
                        from_version=r["from_version"],
                        to_version=r["to_version"],
                        fitness_before=r["fitness_before"],
                        fitness_after=r.get("fitness_after"),
                        accepted=r["accepted"],
                    )
        else:
            print("[DARWIN] All agents above fitness threshold — no evolution needed")

        # Print team health
        report = await darwin.get_evolution_report()
        print(f"\n{report}")

        existing = state.get("evolution_records", [])
        return {"evolution_records": existing + records, "darwin_triggered": bool(records)}

    return _darwin_check


def _make_build_dispatch(analytics: PipelineAnalytics | None):
    async def _node(state: AgentState) -> Dict[str, Any]:
        print("\n[PIPELINE] ═══ PHASE 2: BUILD (parallel) ═══")
        if analytics:
            await analytics.start_phase("BUILD")
        return {"current_phase": 2}
    return _node


def _make_build_sync(analytics: PipelineAnalytics | None):
    async def _node(state: AgentState) -> Dict[str, Any]:
        print("[PIPELINE] ═══ Build phase complete — syncing outputs ═══")
        if analytics:
            await analytics.end_phase("BUILD", ["PIXEL", "FORGE", "VAULT", "CIPHER", "WEAVE"])
        return {"current_phase": 2}
    return _node


def _make_quality_gate(analytics: PipelineAnalytics | None):
    async def _node(state: AgentState) -> Dict[str, Any]:
        echo_reports = state.get("echo_reports", [])

        # Get actual ECHO composite scores from PROBE and LENS reports
        probe_reports = [r for r in echo_reports if r.get("agent_id") == "PROBE"]
        lens_reports  = [r for r in echo_reports if r.get("agent_id") == "LENS"]

        probe_score = probe_reports[-1]["composite_score"] if probe_reports else 0.0
        lens_score  = lens_reports[-1]["composite_score"]  if lens_reports  else 0.0

        retry_count = state.get("quality_retry_count", 0)

        passed = (
            probe_score >= config.QUALITY_GATE["min_probe_score"] and
            lens_score  >= config.QUALITY_GATE["min_lens_score"]
        )

        if passed:
            print(f"[QUALITY GATE] ✅ PASS — probe: {probe_score:.1f}, lens: {lens_score:.1f}")
        else:
            print(f"[QUALITY GATE] ❌ FAIL — probe: {probe_score:.1f}, lens: {lens_score:.1f}")

        if analytics:
            import asyncio
            asyncio.create_task(analytics.emit_quality_gate(
                attempt=retry_count + 1,
                probe_score=probe_score,
                lens_score=lens_score,
                passed=passed,
                retry_count=retry_count,
            ))

        return {
            "quality_gate_passed": passed,
            "quality_retry_count": retry_count + (0 if passed else 1),
            "current_phase": 3,
        }
    return _node


async def _write_artifact(path: Path, content: str):
    """Fire-and-forget artifact write — never blocks the pipeline."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"  [DISK] {path}")
    except Exception as e:
        print(f"  [DISK ERROR] {path}: {e}")

async def _finalize(state: AgentState, analytics: PipelineAnalytics | None = None) -> Dict[str, Any]:
    """Compile the final report for the human. Persist artifacts to disk (async, non-blocking)."""
    import hashlib
    from pathlib import Path

    project_id = state.get("project_id", "unknown")
    intent_slug = hashlib.md5(state.get("human_intent", "unknown")[:30].encode()).hexdigest()[:8]
    artifact_dir = Path(f"./artifacts/{project_id}_{intent_slug}")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Persist all deliverables — fire-and-forget, never block pipeline
    file_deliverables = {
        "prd.md": state.get("prd"),
        "architecture.md": state.get("architecture"),
        "api_contract.md": state.get("api_contract"),
        "data_schema.md": state.get("data_schema"),
        "migrations.sql": state.get("database_migrations"),
        "security_audit.md": state.get("security_audit"),
    }
    for name, content in file_deliverables.items():
        if content:
            path = artifact_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            asyncio.create_task(_write_artifact(path, content))

    # Write code bundles to their respective directories
    code_bundles = {
        "frontend/index.html": state.get("frontend_code"),
        "backend/main.py": state.get("backend_code"),
        "tests/test_suite.py": state.get("test_suite"),
        "deployment/docker-compose.yml": state.get("deployment_config"),
        "observability/prometheus.yml": state.get("observability_config"),
        "docs/README.md": state.get("documentation"),
    }
    for name, content in code_bundles.items():
        if content:
            path = artifact_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            asyncio.create_task(_write_artifact(path, content))

    # Build summary
    echo_reports = state.get("echo_reports", [])
    avg_score = (
        sum(r["composite_score"] for r in echo_reports) / len(echo_reports)
        if echo_reports else 0.0
    )

    lines = [
        "═══════════════════════════════════════════════════",
        "           AGENT COMMAND — BUILD COMPLETE          ",
        "═══════════════════════════════════════════════════",
        f"Project ID:     {state.get('project_id', 'N/A')}",
        f"Intent:         {state.get('human_intent', 'N/A')[:80]}",
        f"Quality Gate:   {'✅ PASSED' if state.get('quality_gate_passed') else '⚠️ ESCALATED'}",
        f"Retries:        {state.get('quality_retry_count', 0)}",
        f"Agent Runs:     {len(echo_reports)}",
        f"Avg Team Score: {avg_score:.2f}/10.0",
        f"Evolution Events: {len(state.get('evolution_records', []))}",
        "───────────────────────────────────────────────────",
        "DELIVERABLES:",
        f"  PRD:              {'✓' if state.get('prd') else '✗'}",
        f"  Architecture:     {'✓' if state.get('architecture') else '✗'}",
        f"  Frontend Code:    {'✓' if state.get('frontend_code') else '✗'}",
        f"  Backend Code:     {'✓' if state.get('backend_code') else '✗'}",
        f"  DB Migrations:    {'✓' if state.get('database_migrations') else '✗'}",
        f"  Security Audit:   {'✓' if state.get('security_audit') else '✗'}",
        f"  AI Modules:       {'✓' if state.get('ai_modules') else '✗'}",
        f"  Test Suite:       {'✓' if state.get('test_suite') else '✗'}",
        f"  Deployment:       {'✓' if state.get('deployment_config') else '✗'}",
        f"  Observability:    {'✓' if state.get('observability_config') else '✗'}",
        f"  Documentation:    {'✓' if state.get('documentation') else '✗'}",
        "═══════════════════════════════════════════════════",
    ]

    report = "\n".join(lines)
    print(f"\n{report}")

    return {"final_report": report, "current_phase": 4}


# ─────────────────────────────────────────────────────────────────────────────
#  Initial State Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_initial_state(human_intent: str, needs_ai: bool = False) -> AgentState:
    """Create a fresh state for a new build from a human intent string."""
    return AgentState(
        messages=[],
        project_id=str(uuid.uuid4())[:8],
        human_intent=human_intent,
        nexus_plan=None,
        current_phase=0,
        quality_gate_passed=False,
        quality_retry_count=0,
        phases={},
        prd=None,
        architecture=None,
        api_contract=None,
        data_schema=None,
        frontend_code=None,
        backend_code=None,
        database_migrations=None,
        security_audit=None,
        ai_modules=None,
        needs_ai_features=needs_ai,
        test_suite=None,
        probe_score=0.0,
        review_report=None,
        lens_score=0.0,
        deployment_config=None,
        observability_config=None,
        documentation=None,
        echo_reports=[],
        run_id=str(uuid.uuid4()),
        evolution_records=[],
        darwin_triggered=False,
        final_report=None,
        error=None,
    )
