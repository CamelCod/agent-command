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
#  Truncation Limits
#  No magic numbers — all limit constants declared here (Pillar VI)
# ─────────────────────────────────────────────────────────────────────────────
MAX_ARCH_LENGTH       = 2000  # Architecture context slice length
MAX_API_LENGTH       = 1500  # API contract slice length
MAX_PRD_LENGTH       = 1000  # PRD slice length
MAX_SCHEMA_LENGTH    = 500   # Data schema slice length
MAX_BACKEND_LENGTH   = 2500  # Backend code slice length
MAX_FRONTEND_LENGTH  = 1000  # Frontend code slice length
MAX_OTHER_LENGTH     = 800   # Catch-all for other context slices
MAX_HUMAN_INTENT     = 200   # Human intent prefix length
MAX_REVIEW_OUTPUT    = 500   # Atlas review fallback output
MAX_DEPLOY_LENGTH    = 1000  # Deployment config slice length
MAX_DEPLOY_SHORT     = 400   # Short deployment config slice


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 0 — Command
# ─────────────────────────────────────────────────────────────────────────────

class Nexus(BaseAgent):
    """NEXUS — Orchestrator. Decomposes human intent into an execution plan."""
    agent_id = "NEXUS"

    def _build_prompt(self, state: AgentState) -> str:
        # -------------------------------------------------------
        # FUNCTION: _build_prompt (NEXUS)
        # GOAL:     Build the system prompt for the orchestrator agent.
        # INPUT:    state (AgentState) — contains human_intent
        # OUTPUT:   Returns str — the prompt to send to the LLM.
        # -------------------------------------------------------
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
    """PRISM — Product Strategist. Converts human intent into a PRD."""
    agent_id = "PRISM"

    def _build_prompt(self, state: AgentState) -> str:
        # -------------------------------------------------------
        # FUNCTION: _build_prompt (PRISM)
        # GOAL:     Build the system prompt for the product strategist.
        # INPUT:    state — contains human_intent and nexus_plan
        # OUTPUT:   Returns str — the prompt to send to the LLM.
        # -------------------------------------------------------
        return f"""Human intent:
{state['human_intent']}

NEXUS Execution Plan:
{state.get('nexus_plan', 'Not available')}

Produce the complete Product Requirements Document (PRD) for this product.
Be specific and buildable. Cut scope ruthlessly for MVP."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"prd": output}


class Atlas(BaseAgent):
    """ATLAS — System Architect. Designs tech stack, API contracts, and data schemas."""
    agent_id = "ATLAS"

    def _build_prompt(self, state: AgentState) -> str:
        # -------------------------------------------------------
        # FUNCTION: _build_prompt (ATLAS)
        # GOAL:     Build the system prompt for the architect agent.
        # INPUT:    state — contains prd and human_intent
        # OUTPUT:   Returns str — the prompt to send to the LLM.
        # -------------------------------------------------------
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
        return "\n".join(section_lines) if section_lines else text[:MAX_REVIEW_OUTPUT]


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 2 — Build (runs in parallel)
# ─────────────────────────────────────────────────────────────────────────────

class Pixel(BaseAgent):
    """PIXEL — Frontend Engineer. Builds UI components and pages from architecture."""
    agent_id = "PIXEL"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""ARCHITECTURE from ATLAS:
{state.get('architecture', 'Not available')[:MAX_ARCH_LENGTH]}

API CONTRACT:
{state.get('api_contract', 'Not available')[:MAX_API_LENGTH]}

PRD requirements:
{state.get('prd', 'Not available')[:MAX_PRD_LENGTH]}

Build the complete frontend application.
Write actual, production-ready React/Next.js code.
Cover: components, state management, routing, API integration, styling."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"frontend_code": output}


class Forge(BaseAgent):
    """FORGE — Backend Engineer. Builds APIs, auth, and integrations from architecture."""
    agent_id = "FORGE"

    def _build_prompt(self, state: AgentState) -> str:
        forge_patch = state.get("forge_patch_notes", "")
        patch_section = ""
        if forge_patch:
            patch_section = f"""
## PRIORITY: Apply these targeted fixes FIRST:
{forge_patch}
---
"""

        return f"""ARCHITECTURE from ATLAS:
{state.get('architecture', 'Not available')[:MAX_ARCH_LENGTH]}

API CONTRACT to implement:
{state.get('api_contract', 'Not available')[:1500]}

DATA SCHEMA from VAULT context:
{state.get('data_schema', 'Not available')[:MAX_SCHEMA_LENGTH]}

PRD requirements:
{state.get('prd', 'Not available')[:MAX_PRD_LENGTH]}
{patch_section}
Build the complete backend application.
Implement every endpoint in the API contract.
Write actual, production-ready code."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"backend_code": output}


class Vault(BaseAgent):
    """VAULT — Database Architect. Designs schemas, migrations, and indexes."""
    agent_id = "VAULT"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""DATABASE SCHEMA from ATLAS:
{state.get('data_schema', 'Not available')}

ARCHITECTURE context:
{state.get('architecture', 'Not available')[:MAX_OTHER_LENGTH]}

PRD features to support:
{state.get('prd', 'Not available')[:MAX_PRD_LENGTH]}

Produce:
1. Complete Prisma schema or SQL migrations
2. Index definitions with rationale
3. Redis cache setup
4. Seed data scripts"""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"database_migrations": output}


class Cipher(BaseAgent):
    """CIPHER — Security Engineer. Audits code and hardens the system against OWASP Top 10."""
    agent_id = "CIPHER"

    def _build_prompt(self, state: AgentState) -> str:
        backend_len = len(state.get("backend_code") or "")
        frontend_len = len(state.get("frontend_code") or "")
        return f"""SECURITY AUDIT REQUEST

Backend code ({backend_len} chars):
{(state.get('backend_code') or '')[:MAX_BACKEND_LENGTH]}

Frontend code ({frontend_len} chars):
{(state.get('frontend_code') or '')[:MAX_FRONTEND_LENGTH]}

Architecture:
{state.get('architecture', 'Not available')[:MAX_OTHER_LENGTH]}

Perform a comprehensive OWASP Top 10 security audit.
Identify vulnerabilities, provide severity ratings, and include fixed code."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"security_audit": output}


class Weave(BaseAgent):
    """WEAVE — AI/ML Engineer. Builds LLM features, RAG pipelines, and AI integrations."""
    agent_id = "WEAVE"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""AI FEATURE IMPLEMENTATION REQUEST

Product intent:
{state['human_intent']}

PRD (AI features section):
{state.get('prd', 'Not available')[:MAX_PRD_LENGTH]}

Architecture context:
{state.get('architecture', 'Not available')[:MAX_OTHER_LENGTH]}

Build the complete AI/ML feature modules.
Include: prompts, RAG pipeline, embeddings, API integration, evals."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"ai_modules": output}


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 3 — Quality Gate (runs in parallel)
# ─────────────────────────────────────────────────────────────────────────────

class Probe(BaseAgent):
    """PROBE — QA Engineer. Writes and runs unit, integration, E2E, and load tests."""
    agent_id = "PROBE"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""QA TEST SUITE REQUEST

Backend code to test:
{(state.get('backend_code') or '')[:MAX_BACKEND_LENGTH]}

Frontend code to test:
{(state.get('frontend_code') or '')[:MAX_FRONTEND_LENGTH]}

PRD acceptance criteria:
{state.get('prd', 'Not available')[:MAX_PRD_LENGTH]}

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
    """LENS — Code Reviewer. Enforces quality standards and architecture adherence."""
    agent_id = "LENS"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""CODE REVIEW REQUEST

Backend code:
{(state.get('backend_code') or '')[:MAX_BACKEND_LENGTH]}

Frontend code:
{(state.get('frontend_code') or '')[:MAX_FRONTEND_LENGTH]}

Architecture spec to validate against:
{state.get('architecture', 'Not available')[:MAX_OTHER_LENGTH]}

Perform a thorough code review.
Score each criterion. Issue a final PASS/BLOCK verdict.

IMPORTANT — Also output a FORGE_PATCH section at the END of your response if there are code issues:

## FORGE_PATCH
1. [FILENAME] Specific fix — one sentence
2. [FILENAME] Another fix
...

Only include FORGE_PATCH if there are actual code issues. If code is good, omit this section entirely."""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        passed = "❌ BLOCK" not in output and ("✅ PASS" in output or "PASS" in output.upper())
        score = 8.0 if passed else 4.0

        # Extract FORGE_PATCH notes for targeted fix
        forge_patch = ""
        if "## FORGE_PATCH" in output:
            parts = output.split("## FORGE_PATCH", 1)
            forge_patch = parts[1].strip()

        return {
            "review_report": output,
            "lens_score": score,
            "forge_patch_notes": forge_patch,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  TIER 4 — Ship
# ─────────────────────────────────────────────────────────────────────────────

class Launch(BaseAgent):
    """LAUNCH — DevOps Engineer. Containerises and deploys the product to production."""
    agent_id = "LAUNCH"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""DEPLOYMENT REQUEST

Project: {state['human_intent'][:MAX_HUMAN_INTENT]}

Architecture:
{state.get('architecture', 'Not available')[:MAX_OTHER_LENGTH]}

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
    """SIGNAL — Observability Engineer. Sets up logging, metrics, and alerting."""
    agent_id = "SIGNAL"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""OBSERVABILITY SETUP REQUEST

Deployment config:
{state.get('deployment_config', 'Not available')[:MAX_DEPLOY_LENGTH]}

Architecture:
{state.get('architecture', 'Not available')[:MAX_OTHER_LENGTH]}

Implement full observability:
1. Structured logging instrumentation
2. Prometheus metrics + Grafana dashboard config
3. Sentry error tracking setup
4. Uptime monitoring + alert rules
5. SLO definitions"""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"observability_config": output}


class Ink(BaseAgent):
    """INK — Technical Writer. Documents the product for users and developers."""
    agent_id = "INK"

    def _build_prompt(self, state: AgentState) -> str:
        return f"""DOCUMENTATION REQUEST

Product: {state['human_intent'][:MAX_HUMAN_INTENT]}

Architecture summary:
{state.get('architecture', 'Not available')[:MAX_OTHER_LENGTH]}

API contract:
{state.get('api_contract', 'Not available')[:MAX_OTHER_LENGTH]}

Deployment info:
{state.get('deployment_config', 'Not available')[:MAX_DEPLOY_SHORT]}

Produce complete documentation:
1. README.md with quick start
2. API reference
3. User guide
4. CHANGELOG.md
5. Operations runbook"""

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        return {"documentation": output}
