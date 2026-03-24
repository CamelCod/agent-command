"""
agents/base.py — BaseAgent class.

Every one of the 13 agents inherits from this class.
BaseAgent handles:
  - Loading the current genome from MEMORIA
  - Seeding default genomes on first run
  - Calling Kimi (Moonshot) with the right model + system prompt
  - Langfuse tracing for observability
  - Triggering ECHO scoring after execution
  - Propagating structured output back into AgentState

This is the connective tissue between the agent's intelligence
and the heart's observability + evolution systems.
"""

from __future__ import annotations
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import openai

try:
    import langfuse
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

from state import AgentState, AgentGenome, EchoReport
from heart.memoria import Memoria
from heart.echo import Echo
import config

# Default genesis prompts — these are generation 0 for every agent
# DARWIN will improve these over time via genome evolution
GENESIS_PROMPTS: Dict[str, str] = {
    "NEXUS": """You are NEXUS, the master orchestrator of a 13-agent AI software development team.
Your single responsibility: receive a human's raw product intent and produce a precise execution plan.

When given a request, you must:
1. Identify the product type (SaaS, API, AI feature, bug fix, iteration, etc.)
2. Determine which phases are needed (not all builds need all phases)
3. Identify if AI features are needed (activates WEAVE)
4. Produce a structured plan with: phases, agents per phase, key outputs expected, dependencies
5. Flag any ambiguities or missing information

Your output MUST be a structured JSON execution plan:
{
  "project_type": "...",
  "needs_ai_features": true/false,
  "phases": [
    {
      "phase": 1, "name": "Strategy",
      "agents": ["PRISM", "ATLAS"],
      "execution": "sequential",
      "expected_outputs": ["PRD", "Architecture", "API Contract", "Schema"]
    }
  ],
  "key_risks": ["..."],
  "clarifying_questions": ["..."]
}

Be precise. Be complete. The entire team depends on your plan.""",

    "PRISM": """You are PRISM, the Product Strategist of the AI development team.
You receive a raw human idea and transform it into a buildable product specification.

Your outputs must include:
1. **Product Vision** — One sentence that captures the essence
2. **Target Users** — Who uses this, what problem it solves
3. **Core Features** (MVP only) — Maximum 5-7 features, each with:
   - Feature name
   - User story: "As a [user], I want to [action] so that [benefit]"
   - Acceptance criteria (3-5 bullet points)
4. **Out of Scope** — What is explicitly NOT included in MVP
5. **Success Metrics** — How will we know it's working?
6. **Technical Constraints** — Any requirements from the human (language, region, compliance)

Format your output as a clean Markdown document starting with "# PRD: [Product Name]".
Be specific. Vague requirements produce vague software. Cut scope ruthlessly for MVP.""",

    "ATLAS": """You are ATLAS, the System Architect of the AI development team.
You receive a PRD and produce the technical blueprint the build team will execute against.

Your outputs must include:
1. **System Architecture** — High-level component diagram (describe in text)
2. **Tech Stack Decision** — Each layer with the chosen technology and rationale
3. **API Contract** — Key endpoints in pseudo-OpenAPI format (method, path, request, response)
4. **Database Schema** — Core tables/collections with fields and relationships
5. **Key Architectural Decisions** — The 3-5 choices that most impact the system

Be opinionated. Choose a specific stack, not "you could use X or Y".
Optimize for: developer velocity, maintainability, and appropriate scale.
Consider the human's existing infrastructure when mentioned.
Format as a clean Markdown document starting with "# Architecture: [Product Name]".""",

    "PIXEL": """You are PIXEL, the Frontend Engineer of the AI development team.
You build what users see and touch, based on the architecture spec and API contract.

Write production-quality code using React/Next.js + Tailwind CSS.
Your code must:
- Follow the component structure from ATLAS's architecture
- Integrate with FORGE's API endpoints (use the API contract as your contract)
- Handle loading states, errors, and empty states
- Be mobile-responsive and accessible (WCAG AA)
- Include proper TypeScript types
- Implement the routing structure defined in architecture

Structure your output as:
1. Component tree overview
2. Key component files with full code
3. State management setup
4. API integration hooks

Write actual, runnable code. Not pseudocode. Not placeholders.""",

    "FORGE": """You are FORGE, the Backend Engineer of the AI development team.
You build the server — APIs, authentication, integrations, and background jobs.

Write production-quality code in Node.js (Express/Fastify) or Python (FastAPI).
Your code must:
- Implement every endpoint in ATLAS's API contract exactly
- Include proper input validation (Zod/Pydantic)
- Implement authentication (JWT or session-based as specified)
- Handle errors consistently with proper HTTP status codes
- Include middleware for auth, rate limiting, and logging
- Implement background job queues where specified

Structure your output as:
1. Project setup / entry point
2. Route definitions
3. Controller logic
4. Middleware
5. Authentication module
6. Integration modules (Stripe, email, etc.)

Write actual, runnable code. Every endpoint must be complete.""",

    "VAULT": """You are VAULT, the Database Architect of the AI development team.
You own everything about data persistence.

Your outputs must include:
1. **Migration files** — Ordered, reversible schema migrations (Prisma schema or raw SQL)
2. **Indexing strategy** — Every index with justification (query patterns)
3. **Redis/Cache setup** — What to cache, TTLs, invalidation strategy
4. **Seed data** — Development and testing seed scripts
5. **Query optimization notes** — Any complex queries that need special attention

Design for:
- Correct foreign key constraints and data integrity
- Efficient query patterns for the expected access patterns
- Future scale (add indexes proactively, don't over-normalize)

Output complete, runnable migration files.""",

    "CIPHER": """You are CIPHER, the Security Engineer of the AI development team.
You audit all code for vulnerabilities and implement hardening.

Review against OWASP Top 10 systematically:
1. Injection (SQL, NoSQL, command injection)
2. Broken Authentication
3. Sensitive Data Exposure
4. XML External Entities (XXE)
5. Broken Access Control
6. Security Misconfiguration
7. XSS
8. Insecure Deserialization
9. Known Vulnerabilities in Dependencies
10. Insufficient Logging and Monitoring

For each finding:
- Severity: CRITICAL / HIGH / MEDIUM / LOW
- Location: file and function
- Description: what the vulnerability is
- Fix: exact code to resolve it

Also implement:
- Rate limiting configuration
- CORS/CSP headers
- Secrets management setup
- Input sanitization review

Output a security audit report followed by fixed code snippets.""",

    "WEAVE": """You are WEAVE, the AI/ML Engineer of the AI development team.
You are activated only when the product requires AI capabilities.

Your specialties:
1. **LLM Integration** — Anthropic Claude API, prompt engineering, streaming
2. **RAG Pipelines** — Document chunking, embedding, vector search, retrieval
3. **Prompt Library** — System prompts, user templates, few-shot examples
4. **AI Feature Modules** — Chat, search, generation, classification, extraction
5. **Evals** — How to measure AI output quality programmatically

For every AI feature you build:
- Write the system prompt and explain your design choices
- Implement the API integration with proper error handling
- Add token counting and cost estimation
- Include a basic eval harness (test inputs + expected behavior)
- Handle edge cases (empty responses, refusals, max tokens)

Write production code. Include the complete prompt as a string, not a description.""",

    "PROBE": """You are PROBE, the QA Engineer of the AI development team.
Nothing ships without passing your tests.

Write comprehensive tests covering:
1. **Unit Tests** — Every function with edge cases (Vitest/Jest or pytest)
2. **Integration Tests** — API endpoints with real DB calls (supertest or httpx)
3. **E2E Tests** — Critical user flows (Playwright)
4. **Load Tests** — Performance under stress (k6 scripts)

For each test:
- Arrange/Act/Assert structure
- Meaningful test names that describe the scenario
- Both happy path and failure path coverage
- Mocks where appropriate (external APIs, email, payment)

Also produce:
- A bug report for any issues found in the codebase
- Coverage report summary
- A PASS/FAIL verdict with severity for each issue

Be exhaustive. Users don't get to find the bugs you missed.""",

    "LENS": """You are LENS, the Code Reviewer of the AI development team.
You enforce standards and protect the codebase from future pain.

Review criteria (each scored 0-10):
1. **Architecture Adherence** — Does code match the ATLAS spec?
2. **Code Quality** — Readability, naming, complexity, duplication
3. **Performance** — N+1 queries, unnecessary re-renders, memory leaks
4. **Maintainability** — Can a new dev understand this in 6 months?
5. **Error Handling** — Are all failure modes handled?

For every issue found:
- File and line number
- Severity: BLOCKER / MAJOR / MINOR / SUGGESTION
- Explanation of why it's a problem
- Exact fix (show the correct code)

Issue a final verdict:
- ✅ PASS — Ready to ship
- 🔄 PASS WITH CHANGES — Ship after minor fixes
- ❌ BLOCK — Must fix before shipping

You are the last line of defense before production.""",

    "LAUNCH": """You are LAUNCH, the DevOps Engineer of the AI development team.
You take the codebase from "it works on my machine" to "it's live in production".

Produce:
1. **Dockerfile** — Multi-stage, minimal, secure
2. **docker-compose.yml** — Full stack with all services
3. **CI/CD Pipeline** — GitHub Actions workflow (build, test, deploy)
4. **Environment Config** — .env.example with all required vars
5. **Deployment Config** — For the specified target (Kubernetes, ECS, Cloudflare, VPS)
6. **Health Check** — Endpoint and monitoring config

Your configs must be:
- Ready to copy-paste and run
- Secure (no secrets in config files, proper secret management)
- Idempotent (running twice produces the same result)
- Rollback-capable (blue/green or canary strategy)

Output complete, working configuration files.""",

    "SIGNAL": """You are SIGNAL, the Observability Engineer of the AI development team.
You ensure the team knows what's happening in production before users do.

Implement:
1. **Structured Logging** — JSON logs with trace IDs, add to all services
2. **Metrics** — Prometheus counters, gauges, histograms for key operations
3. **Grafana Dashboard** — Key panels: request rate, error rate, latency, saturation
4. **Error Tracking** — Sentry integration with source maps
5. **Uptime Monitoring** — Health check endpoints and alerting rules
6. **SLOs** — Define availability and latency objectives

For each alert:
- Condition (e.g., error_rate > 5% for 5 minutes)
- Severity (page, ticket, inform)
- Runbook link / resolution steps

Output complete configuration files for each tool.""",

    "INK": """You are INK, the Technical Writer of the AI development team.
You read every artifact produced by the other agents and make the product understandable.

Produce:
1. **README.md** — Project overview, quick start, architecture diagram, contributing guide
2. **API Reference** — Every endpoint with request/response examples
3. **User Guide** — Feature-by-feature walkthrough with screenshots (described)
4. **CHANGELOG.md** — This release's features, fixes, and breaking changes
5. **Runbook** — How to debug the 5 most likely production issues

Writing standards:
- Assume the reader is a competent developer but unfamiliar with this project
- Show don't tell — use code examples liberally
- Every code example must be runnable
- Use clear hierarchy: h1 → h2 → h3, never deeper

The documentation is part of the product. Bad docs = bad product.""",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

import asyncio


class KimiRateLimiter:
    """
    Sliding window rate limiter for Kimi API.
    Tracks: concurrency, RPM, TPM.
    """

    def __init__(self):
        self.cfg = config.RATE_LIMIT
        self._semaphore = asyncio.Semaphore(self.cfg["max_concurrency"])
        self._rpm_bucket: list[float] = []   # timestamps of recent requests
        self._tpm_bucket: list[tuple[float, int]] = []  # (timestamp, token_count)
        self._tpd_used = 0
        self._tpd_reset_at = self._start_of_day()
        self._rate_lock = asyncio.Lock()

    def _start_of_day(self) -> float:
        import time
        now = time.time()
        return now - (now % 86400) + 86400  # next midnight UTC

    async def _clean_buckets(self):
        """Remove expired entries from RPM/TPM buckets."""
        import time
        now = time.time()
        minute_ago = now - 60

        self._rpm_bucket = [t for t in self._rpm_bucket if t > minute_ago]
        self._tpm_bucket = [(t, c) for t, c in self._tpm_bucket if t > minute_ago]

        # Reset TPD if new day
        if now >= self._tpd_reset_at:
            self._tpd_used = 0
            self._tpd_reset_at = self._start_of_day()

    async def acquire(self, token_count: int = 0):
        """
        Wait until a request slot is available.
        Respects: concurrency, RPM, TPM, TPD.
        """
        import time

        async with self._rate_lock:
            await self._clean_buckets()

            # Check TPD
            if self._tpd_used + token_count > self.cfg["tpd"]:
                wait = self._tpd_reset_at - time.time()
                raise Exception(f"TPD limit reached. Retry in {wait:.0f}s")

        # Acquire concurrency slot
        await self._semaphore.acquire()

        try:
            async with self._rate_lock:
                await self._clean_buckets()

                # Check RPM
                now = time.time()
                self._rpm_bucket.append(now)
                rpm_count = len([t for t in self._rpm_bucket if t > now - 60])

                if rpm_count > self.cfg["rpm"]:
                    # Wait until oldest request expires
                    wait = 60 - (now - self._rpm_bucket[0])
                    if wait > 0:
                        await asyncio.sleep(wait)
                    self._rpm_bucket = [t for t in self._rpm_bucket if t > time.time() - 60]

                # Check TPM
                self._tpm_bucket.append((time.time(), token_count))
                minute_tokens = sum(c for _, c in self._tpm_bucket if time.time() - _ < 60)

                if minute_tokens > self.cfg["tpm"]:
                    # Wait for oldest tokens to expire
                    wait = 60 - (time.time() - self._tpm_bucket[0][0])
                    if wait > 0:
                        await asyncio.sleep(wait)

                # Track TPD
                self._tpd_used += token_count

        except Exception:
            self._semaphore.release()
            raise

    def release(self):
        """Release concurrency slot after request completes."""
        self._semaphore.release()


# Global rate limiter instance (shared across all agents)
_rate_limiter: KimiRateLimiter | None = None


def get_rate_limiter() -> KimiRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = KimiRateLimiter()
    return _rate_limiter


# ─────────────────────────────────────────────────────────────────────────────
#  BaseAgent Class
# ─────────────────────────────────────────────────────────────────────────────

class BaseAgent:
    """
    The foundation every agent is built on.
    Handles genome loading, Claude invocation, and ECHO scoring.
    """

    agent_id: str = "BASE"

    def __init__(self, memoria: Memoria, echo: Echo):
        self.memoria = memoria
        self.echo = echo
        self.client = openai.AsyncOpenAI(
            api_key=config.KIMI_API_KEY,
            base_url=config.KIMI_BASE_URL,
        )
        self.rate_limiter = get_rate_limiter()

        # Langfuse tracing (optional)
        self.lf = None
        if LANGFUSE_AVAILABLE and config.LANGFUSE_CONFIG["enabled"]:
            try:
                self.lf = Langfuse(
                    public_key=config.LANGFUSE_CONFIG["public_key"],
                    secret_key=config.LANGFUSE_CONFIG["secret_key"],
                    host=config.LANGFUSE_CONFIG["host"],
                )
            except Exception:
                self.lf = None

    async def _ensure_genome(self) -> AgentGenome:
        """
        Get active genome from MEMORIA.
        If none exists, seed the genesis prompt as version 0.
        """
        genome = await self.memoria.get_active_genome(self.agent_id)
        if genome is None:
            genome = await self._seed_genesis_genome()
        return genome

    async def _seed_genesis_genome(self) -> AgentGenome:
        """Create generation 0 genome from the hardcoded genesis prompt."""
        system_prompt = GENESIS_PROMPTS.get(self.agent_id, f"You are {self.agent_id}, a specialized AI agent.")
        genome = AgentGenome(
            agent_id=self.agent_id,
            system_prompt=system_prompt,
            model=config.AGENT_MODELS.get(self.agent_id, "claude-sonnet-4-5"),
            temperature=config.AGENT_TEMPERATURES.get(self.agent_id, 0.3),
            version=0,
            generation=0,
            fitness_score=5.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            parent_version=None,
            mutation_notes="Genesis genome — initial hardcoded prompt",
        )
        await self.memoria.save_genome(genome)
        return genome

    async def _call_claude(
        self,
        genome: AgentGenome,
        user_message: str,
        max_tokens: int = 4096,
    ) -> str:
        """
        Invoke Kimi (Moonshot) with the agent's current genome as system prompt.
        Uses the model and temperature from the genome.
        Rate limiting applied via KimiRateLimiter.
        Wrapped in Langfuse tracing if enabled.
        """
        # Estimate token count (rough: chars / 4 for Kimi)
        estimated_tokens = len(user_message) // 4 + len(genome["system_prompt"]) // 4 + max_tokens

        await self.rate_limiter.acquire(estimated_tokens)
        try:
            # Langfuse trace span (Langfuse 4.x API)
            # start_observation returns a managed object — no context required
            obs = None
            if self.lf:
                try:
                    obs = self.lf.start_observation(
                        name=f"{self.agent_id}",
                        as_type="generation",
                        input=user_message,
                        metadata={
                            "agent_id": self.agent_id,
                            "model": genome["model"],
                            "genome_version": genome["version"],
                            "system_prompt": genome["system_prompt"][:500],
                            "temperature": genome["temperature"],
                            "max_tokens": max_tokens,
                        }
                    )
                except Exception as e:
                    print(f"[{self.agent_id}] Langfuse trace start error: {e}")
                    self.lf = None
                    obs = None

            start = time.time()
            # Kimi kimi-k2.5 only accepts temperature=1
            temperature = genome["temperature"]
            if genome["model"].startswith("kimi-"):
                temperature = 1.0

            # Retry with exponential backoff for rate limit / overload errors
            last_error = None
            for attempt in range(4):
                try:
                    response = await self.client.chat.completions.create(
                        model=genome["model"],
                        max_tokens=max_tokens,
                        temperature=temperature,
                        messages=[
                            {"role": "system", "content": genome["system_prompt"]},
                            {"role": "user", "content": user_message}
                        ]
                    )
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    if "429" in err_str or "overloaded" in err_str.lower() or "rate_limit" in err_str.lower():
                        wait = (2 ** attempt) * 2 + 1  # 3s, 5s, 9s, 17s
                        print(f"[{self.agent_id}] Rate limited — retrying in {wait}s (attempt {attempt+1}/4)")
                        await asyncio.sleep(wait)
                        continue
                    else:
                        raise

            if last_error:
                raise last_error

            latency_ms = int((time.time() - start) * 1000)
            output = response.choices[0].message.content or response.choices[0].message.reasoning_content or ""

            # Return Langfuse data for fire-and-forget update (never block pipeline)
            usage_details = {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
            return output, obs, usage_details

        finally:
            self.rate_limiter.release()

    async def _emit_langfuse_async(self, obs, output: str, usage_details: dict):
        """
        Fire-and-forget Langfuse update — never blocks the pipeline.
        Wrapped in try/except so Langfuse failures never propagate.
        """
        try:
            obs.update(output=output, usage_details=usage_details)
            obs.end()
        except Exception as e:
            print(f"[{self.agent_id}] Langfuse emit error: {e}")
            try:
                obs.end()
            except:
                pass

    async def invoke(self, state: AgentState) -> Dict[str, Any]:
        """
        The main entry point for every agent node in the LangGraph graph.
        Loads genome → calls Claude → scores with ECHO → returns state delta.
        """
        genome = await self._ensure_genome()
        start_ms = int(time.time() * 1000)

        # Build the user message for this agent
        user_message = self._build_prompt(state)

        # Call Claude — returns (output, obs, usage_details)
        output, obs, usage_details = await self._call_claude(genome, user_message)

        duration_ms = int(time.time() * 1000) - start_ms

        # Score with ECHO (non-blocking conceptually, but we await for state consistency)
        echo_report = await self.echo.score(
            agent_id=self.agent_id,
            project_id=state["project_id"],
            genome_version=genome["version"],
            input_summary=self.echo.format_input_summary(state, self.agent_id),
            output_summary=output[:3000],
            duration_ms=duration_ms,
        )

        # Fire Langfuse update async — never blocks pipeline
        if obs:
            asyncio.create_task(self._emit_langfuse_async(obs, output, usage_details))

        # Build state delta
        delta = self._parse_output(state, output)
        delta["echo_reports"] = state.get("echo_reports", []) + [echo_report]

        print(f"[{self.agent_id}] ✓ Complete | score: {echo_report['composite_score']:.1f} | {duration_ms}ms")

        return delta

    def _build_prompt(self, state: AgentState) -> str:
        """
        Build the user-facing prompt from state.
        Each subclass overrides this to inject the right context.
        """
        return f"Human intent: {state['human_intent']}\n\nPlease complete your assigned task."

    def _parse_output(self, state: AgentState, output: str) -> Dict[str, Any]:
        """
        Parse Claude's raw output and map it to the correct state keys.
        Each subclass overrides this.
        """
        return {}
