"""
heart/analytics.py — Analytics tracking for Agent Command pipeline.

Submits metrics to:
1. Langfuse Scores — ECHO composite scores as scores on traces
2. Pipeline events JSONL — phase transitions, gate decisions, evolution events
3. Stdout — real-time metrics stream for monitoring

Usage:
    analytics = PipelineAnalytics(memoria)
    await analytics.emit_agent_completed(agent_id, duration_ms, echo_report)
    await analytics.emit_phase_transition(phase_name, agents, duration_s)
    await analytics.emit_quality_gate(attempt, probe_score, lens_score, passed)
"""

from __future__ import annotations
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path

import httpx

from state import EchoReport
import config


class PipelineAnalytics:
    """
    Collects and emits pipeline metrics to multiple backends.

    Backends:
    - Langfuse Scores: ECHO quality scores submitted as Langfuse scores
    - JSONL file: pipeline events for BI/ Grafana ingestion
    - Stdout: real-time progress stream
    """

    def __init__(self, memoria):
        self.memoria = memoria
        self.lf_config = config.LANGFUSE_CONFIG
        self.events_path = Path("./pipeline_events.jsonl")
        self._http = httpx.AsyncClient(timeout=30.0)

        # Track phase start times for duration calculation
        self._phase_starts: Dict[str, float] = {}

        # Metrics accumulators
        self._build_start: Optional[float] = None
        self._build_end: Optional[float] = None

    # ─────────────────────────────────────────────────────────────────────────
    #  Langfuse Scores
    # ─────────────────────────────────────────────────────────────────────────

    async def _submit_langfuse_score(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: str = "",
    ):
        """Submit a score to Langfuse for a trace."""
        if not self.lf_config["enabled"]:
            return

        try:
            await self._http.post(
                f"{self.lf_config['host']}/api/public/scores",
                auth=(
                    self.lf_config["public_key"],
                    self.lf_config["secret_key"],
                ),
                json=[{
                    "traceId": trace_id,
                    "name": name,
                    "value": value,
                    "comment": comment,
                    "source": "agent_command",
                }],
            )
        except httpx.HTTPError as e:
            print(f"[ANALYTICS] Langfuse score submission failed: {e}")

    async def emit_agent_completed(
        self,
        agent_id: str,
        trace_id: str,
        duration_ms: int,
        echo_report: Optional[EchoReport] = None,
    ):
        """Called after each agent completes."""
        score = echo_report["composite_score"] if echo_report else 5.0

        event = {
            "event": "agent_completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "trace_id": trace_id,
            "duration_ms": duration_ms,
            "composite_score": score,
            "tier": config.AGENT_TIERS.get(agent_id, "??"),
            "genome_version": echo_report.get("genome_version", 0) if echo_report else 0,
        }

        if echo_report:
            event["scores"] = {
                "quality": echo_report["score_quality"],
                "completeness": echo_report["score_completeness"],
                "contract_adherence": echo_report["score_contract_adherence"],
                "efficiency": echo_report["score_efficiency"],
                "innovation": echo_report["score_innovation"],
            }
            event["assessment"] = echo_report.get("assessment", "")

        await self._emit_jsonl(event)
        print(
            f"[ANALYTICS] {agent_id} | score: {score:.1f} | {duration_ms}ms"
        )

        # Submit score to Langfuse
        await self._submit_langfuse_score(
            trace_id=trace_id,
            name=f"echo_{agent_id.lower()}_score",
            value=score,
            comment=echo_report.get("assessment", "") if echo_report else "",
        )

    # ─────────────────────────────────────────────────────────────────────────
    #  Phase Transitions
    # ─────────────────────────────────────────────────────────────────────────

    async def start_phase(self, phase_name: str):
        """Mark when a phase starts."""
        self._phase_starts[phase_name] = time.time()
        event = {
            "event": "phase_started",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase_name,
        }
        await self._emit_jsonl(event)
        print(f"[ANALYTICS] Phase started: {phase_name}")

    async def end_phase(self, phase_name: str, agents: list[str]):
        """Mark when a phase ends and emit summary."""
        if phase_name not in self._phase_starts:
            return

        duration_s = time.time() - self._phase_starts[phase_name]
        event = {
            "event": "phase_completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase_name,
            "agents": agents,
            "duration_seconds": round(duration_s, 1),
        }
        await self._emit_jsonl(event)
        print(
            f"[ANALYTICS] Phase completed: {phase_name} | {duration_s:.0f}s | agents: {', '.join(agents)}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    #  Quality Gate
    # ─────────────────────────────────────────────────────────────────────────

    async def emit_quality_gate(
        self,
        attempt: int,
        probe_score: float,
        lens_score: float,
        passed: bool,
        retry_count: int,
    ):
        """Emit quality gate decision."""
        threshold = config.QUALITY_GATE["min_probe_score"]
        event = {
            "event": "quality_gate",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attempt": attempt,
            "probe_score": probe_score,
            "lens_score": lens_score,
            "threshold": threshold,
            "passed": passed,
            "retry_count": retry_count,
        }
        await self._emit_jsonl(event)

        status = "✅ PASS" if passed else "❌ FAIL"
        print(
            f"[ANALYTICS] Quality gate {attempt} | probe: {probe_score:.1f} | lens: {lens_score:.1f} | {status}"
        )

        # Submit quality gate score to Langfuse
        gate_trace_id = f"quality_gate_attempt_{attempt}"
        await self._submit_langfuse_score(
            trace_id=gate_trace_id,
            name="quality_gate_passed",
            value=1.0 if passed else 0.0,
            comment=f"probe={probe_score:.1f} lens={lens_score:.1f}",
        )

    # ─────────────────────────────────────────────────────────────────────────
    #  Evolution Events
    # ─────────────────────────────────────────────────────────────────────────

    async def emit_evolution(
        self,
        agent_id: str,
        from_version: int,
        to_version: int,
        fitness_before: float,
        fitness_after: Optional[float],
        accepted: bool,
    ):
        """Emit when DARWIN evolves an agent."""
        event = {
            "event": "evolution",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "from_version": from_version,
            "to_version": to_version,
            "fitness_before": fitness_before,
            "fitness_after": fitness_after,
            "accepted": accepted,
        }
        await self._emit_jsonl(event)

        delta = f"+{fitness_after - fitness_before:.2f}" if fitness_after else "?"
        status = "✓ accepted" if accepted else "✗ rejected"
        print(
            f"[ANALYTICS] DARWIN evolved {agent_id} | v{from_version}→v{to_version} | "
            f"fitness {fitness_before:.2f}→{fitness_after or '?'} ({delta}) | {status}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    #  Build Summary
    # ─────────────────────────────────────────────────────────────────────────

    async def start_build(self, project_id: str, intent: str):
        """Mark build start."""
        self._build_start = time.time()
        event = {
            "event": "build_started",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project_id": project_id,
            "intent": intent[:100],
        }
        await self._emit_jsonl(event)
        print(f"[ANALYTICS] Build started: {project_id}")

    async def end_build(
        self,
        project_id: str,
        passed: bool,
        escalation: bool,
        total_agents: int,
        total_retries: int,
        evolution_count: int,
        deliverables: Dict[str, bool],
    ):
        """Emit final build summary."""
        duration_s = time.time() - self._build_start if self._build_start else 0
        event = {
            "event": "build_completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project_id": project_id,
            "duration_seconds": round(duration_s, 1),
            "passed": passed,
            "escalation": escalation,
            "total_agents": total_agents,
            "total_retries": total_retries,
            "evolution_count": evolution_count,
            "deliverables": deliverables,
        }
        await self._emit_jsonl(event)

        status = "✅ PASS" if passed else ("⚠️ ESCALATED" if escalation else "❌ FAIL")
        print(
            f"[ANALYTICS] Build complete: {project_id} | {duration_s/60:.1f}min | "
            f"{status} | {total_agents} agents | {total_retries} retries | "
            f"{evolution_count} evolutions"
        )

    # ─────────────────────────────────────────────────────────────────────────
    #  JSONL helper
    # ─────────────────────────────────────────────────────────────────────────

    async def _emit_jsonl(self, event: dict):
        """Append event to JSONL file (non-blocking)."""
        try:
            content = json.dumps(event) + "\n"
            await asyncio.to_thread(self._write_jsonl, self.events_path, content)
        except Exception as e:
            print(f"[ANALYTICS] JSONL write failed: {e}")

    def _write_jsonl(self, path: Path, content: str):
        """Blocking file write helper (runs in thread pool)."""
        with open(path, "a") as f:
            f.write(content)

    # ─────────────────────────────────────────────────────────────────────────
    #  Cleanup
    # ─────────────────────────────────────────────────────────────────────────

    async def close(self):
        await self._http.aclose()
