"""
agents/team.py — All 13 specialized agents.

Each agent is a thin subclass of BaseAgent.
The intelligence lives in the genome (system prompt).
The structure lives here (_build_prompt + _parse_output).
"""

from __future__ import annotations
from typing import Dict, Any
from agents.base import BaseAgent
from state import AgentState


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 0 — Command
# ─────────────────────────────────────────────────────────────────────────────

class Nexus(BaseAgent):
    agent_id = "NEXUS"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""Human intent (raw):
{state['human_intent']}

Produce a complete execution plan for the agent team.
Return a structured JSON execution plan as specified in your instructions."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"nexus_plan": output}


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 1 — Strategy
# ─────────────────────────────────────────────────────────────────────────────

class Prism(BaseAgent):
    agent_id = "PRISM"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""Human intent:
{state['human_intent']}

NEXUS Execution Plan:
{state.get('nexus_plan', 'Not available')}

Produce the complete Product Requirements Document (PRD) for this product.
Be specific and buildable. Cut scope ruthlessly for MVP."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"prd": output}


class Atlas(BaseAgent):
    agent_id = "ATLAS"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""PRD from PRISM:
{state.get('prd', 'No PRD available')}

Human intent context:
{state['human_intent']}

Produce the complete system architecture document including:
- Tech stack decisions
- API contract (key endpoints)
- Database schema
- Component topology

Be specific and opinionated. The build team will execute exactly what you specify."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        # Atlas output contains architecture, API contract, and schema
        # In a real system you'd parse sections — here we store the full output
        return {
            "architecture": output,
            "api_contract": self._extract_section(output, "API Contract", "API"),
            "data_schema": self._extract_section(output, "Database Schema", "Schema"),
        }

    def _extract_section(self, text: str, *headers: str) -> str:
        """Try to extract a section from a markdown document."""
        lines = text.split("\n")
        in_section = False
        section_lines = []
        for line in lines:
            matched = False
            for header in headers:
                if f"# {header}" in line or f"## {header}" in line:
                    in_section = True
                    section_lines = [line]
                    matched = True
                    break
            if not matched and in_section:
                if line.startswith("# ") and section_lines:
                    break  # Next top-level section
                section_lines.append(line)
        return "\n".join(section_lines) if section_lines else text[:500]


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 2 — Build (runs in parallel)
# ─────────────────────────────────────────────────────────────────────────────

class Pixel(BaseAgent):
    agent_id = "PIXEL"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""ARCHITECTURE from ATLAS:
{state.get('architecture', 'Not available')[:2000]}

API CONTRACT:
{state.get('api_contract', 'Not available')[:1000]}

PRD requirements:
{state.get('prd', 'Not available')[:1000]}

Build the complete frontend application.
Write actual, production-ready React/Next.js code.
Cover: components, state management, routing, API integration, styling."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"frontend_code": output}


class Forge(BaseAgent):
    agent_id = "FORGE"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""ARCHITECTURE from ATLAS:
{state.get('architecture', 'Not available')[:2000]}

API CONTRACT to implement:
{state.get('api_contract', 'Not available')[:1500]}

DATA SCHEMA from VAULT context:
{state.get('data_schema', 'Not available')[:500]}

PRD requirements:
{state.get('prd', 'Not available')[:500]}

Build the complete backend application.
Implement every endpoint in the API contract.
Write actual, production-ready code."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"backend_code": output}


class Vault(BaseAgent):
    agent_id = "VAULT"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""DATABASE SCHEMA from ATLAS:
{state.get('data_schema', 'Not available')}

ARCHITECTURE context:
{state.get('architecture', 'Not available')[:1000]}

PRD features to support:
{state.get('prd', 'Not available')[:500]}

Produce:
1. Complete Prisma schema or SQL migrations
2. Index definitions with rationale
3. Redis cache setup
4. Seed data scripts"""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"database_migrations": output}


class Cipher(BaseAgent):
    agent_id = "CIPHER"

    def _build_prompt(self, state: AgentState) -> str:
        backend_len = len(state.get("backend_code") or "")
        frontend_len = len(state.get("frontend_code") or "")
        return f"""SECURITY AUDIT REQUEST

Backend code ({backend_len} chars):
{(state.get('backend_code') or '')[:2500]}

Frontend code ({frontend_len} chars):
{(state.get('frontend_code') or '')[:1000]}

Architecture:
{state.get('architecture', 'Not available')[:500]}

Perform a comprehensive OWASP Top 10 security audit.
Identify vulnerabilities, provide severity ratings, and include fixed code."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"security_audit": output}


class Weave(BaseAgent):
    agent_id = "WEAVE"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""AI FEATURE IMPLEMENTATION REQUEST

Product intent:
{state['human_intent']}

PRD (AI features section):
{state.get('prd', 'Not available')[:1000]}

Architecture context:
{state.get('architecture', 'Not available')[:1000]}

Build the complete AI/ML feature modules.
Include: prompts, RAG pipeline, embeddings, API integration, evals."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"ai_modules": output}


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 3 — Quality Gate (runs in parallel)
# ─────────────────────────────────────────────────────────────────────────────

class Probe(BaseAgent):
    agent_id = "PROBE"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""QA TEST SUITE REQUEST

Backend code to test:
{(state.get('backend_code') or '')[:2500]}

Frontend code to test:
{(state.get('frontend_code') or '')[:1000]}

PRD acceptance criteria:
{state.get('prd', 'Not available')[:1000]}

Write comprehensive tests: unit, integration, E2E, and load tests.
Issue a PASS or BLOCK verdict with justification."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        # Parse PASS/BLOCK from output
        passed = "❌ BLOCK" not in output and ("✅ PASS" in output or "PASS" in output.upper())
        score = 8.0 if passed else 4.0
        return {
            "test_suite": output,
            "probe_score": score,
        }


class Lens(BaseAgent):
    agent_id = "LENS"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""CODE REVIEW REQUEST

Backend code:
{(state.get('backend_code') or '')[:2500]}

Frontend code:
{(state.get('frontend_code') or '')[:1000]}

Architecture spec to validate against:
{state.get('architecture', 'Not available')[:800]}

Perform a thorough code review.
Score each criterion. Issue a final PASS/BLOCK verdict."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        passed = "❌ BLOCK" not in output and ("✅ PASS" in output or "PASS" in output.upper())
        score = 8.0 if passed else 4.0
        return {
            "review_report": output,
            "lens_score": score,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 4 — Ship
# ─────────────────────────────────────────────────────────────────────────────

class Launch(BaseAgent):
    agent_id = "LAUNCH"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""DEPLOYMENT REQUEST

Project: {state['human_intent'][:200]}

Architecture:
{state.get('architecture', 'Not available')[:1000]}

Quality gate: {'PASSED ✅' if state.get('quality_gate_passed') else 'PENDING'}

Produce:
1. Dockerfile (multi-stage)
2. docker-compose.yml
3. GitHub Actions CI/CD workflow
4. Environment configuration (.env.example)
5. Deployment runbook"""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"deployment_config": output}


class Signal(BaseAgent):
    agent_id = "SIGNAL"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""OBSERVABILITY SETUP REQUEST

Deployment config:
{state.get('deployment_config', 'Not available')[:1000]}

Architecture:
{state.get('architecture', 'Not available')[:800]}

Implement full observability:
1. Structured logging instrumentation
2. Prometheus metrics + Grafana dashboard config
3. Sentry error tracking setup
4. Uptime monitoring + alert rules
5. SLO definitions"""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"observability_config": output}


class Ink(BaseAgent):
    agent_id = "INK"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""DOCUMENTATION REQUEST

Product: {state['human_intent'][:200]}

Architecture summary:
{state.get('architecture', 'Not available')[:800]}

API contract:
{state.get('api_contract', 'Not available')[:800]}

Deployment info:
{state.get('deployment_config', 'Not available')[:400]}

Produce complete documentation:
1. README.md with quick start
2. API reference
3. User guide
4. CHANGELOG.md
5. Operations runbook"""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"documentation": output}
