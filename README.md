# AGENT COMMAND
### A self-evolving AI software development team built on LangGraph

> You speak. NEXUS listens. 13 agents build. ECHO watches. DARWIN evolves.

---

## Architecture

```
YOU
 │  (plain language intent)
 ▼
NEXUS (T0 — Commander)
 │  Decomposes intent → execution plan
 ▼
┌─ PHASE 1: STRATEGY ─────────────────────────────┐
│  PRISM → Product Requirements Document            │
│  ATLAS → Architecture + API Contract + Schema     │
└─────────────────────────────────────────────────┘
 ▼
┌─ PHASE 2: BUILD (parallel) ─────────────────────┐
│  PIXEL   → Frontend code (React/Next.js)         │
│  FORGE   → Backend code (FastAPI)                 │
│  VAULT   → Database migrations (Prisma/SQL)      │
│  CIPHER  → Security audit (OWASP Top 10)         │
│  WEAVE   → AI modules (conditional)             │
└─────────────────────────────────────────────────┘
 ▼
┌─ PHASE 3: QUALITY GATE ──────────────────────────┐
│  PROBE  → Test suite + coverage                   │
│  LENS   → Code review + standards                │
│  ↓  Both must PASS — else retry or escalate       │
└─────────────────────────────────────────────────┘
 ▼
┌─ PHASE 4: SHIP ─────────────────────────────────┐
│  LAUNCH → Dockerfile, CI/CD, deployment          │
│  SIGNAL → Logging, metrics, alerts               │
│  INK    → README, API docs, user guide          │
└─────────────────────────────────────────────────┘
 ▼
┌─ HEART: SELF-EVOLUTION ─────────────────────────┐
│  ECHO   → Scores every agent run (5 dimensions) │
│  DARWIN → Reads scores, mutates weak prompts    │
│  MEMORIA→ Persists genomes + history (SQLite)   │
└─────────────────────────────────────────────────┘
```

## Models

All agents use **Moonshot AI (kimi-k2.5)** via a server-side proxy.
The API key lives on the server — never exposed to the browser.

## Setup

```bash
# Install (editable)
pip install -e .

# Or install from PyPI (after first publish)
pip install agent-command

# Configure environment
cp .env.example .env
# Edit .env — set MOONSHOT_API_KEY
```

## Usage

### CLI
```bash
# Build something
agent-command "Build a SaaS for UAE construction tenders"

# With AI features (activates WEAVE)
agent-command "Build a document Q&A system" --ai

# Check team health / fitness scores
agent-command --health

# Force evolve all agents
agent-command --evolve

# See an agent's evolution history
agent-command --history FORGE

# Interactive REPL
agent-command --interactive
```

### Interactive Mode Commands
```
/health             → team fitness dashboard
/evolve             → force evolve all agents
/history <AGENT>    → show agent's evolution history
/quit               → exit
```

### HTTP Server (API + Frontend)
```bash
agent-server
# → http://localhost:8765/     (build monitoring dashboard)
# → http://localhost:8765/ui   (AgentCraft frontend)
```

## Agent Roster

| Agent | Tier | Role | Model |
|-------|------|------|-------|
| NEXUS | T0 | Orchestrator | kimi-k2.5 |
| PRISM | T1 | Product Strategy | kimi-k2.5 |
| ATLAS | T1 | System Architecture | kimi-k2.5 |
| PIXEL | T2 | Frontend Engineer | kimi-k2.5 |
| FORGE | T2 | Backend Engineer | kimi-k2.5 |
| VAULT | T2 | Database Architect | kimi-k2.5 |
| CIPHER | T2 | Security Engineer | kimi-k2.5 |
| WEAVE | T2 | AI/ML Engineer | kimi-k2.5 |
| PROBE | T3 | QA Engineer | kimi-k2.5 |
| LENS | T3 | Code Reviewer | kimi-k2.5 |
| LAUNCH | T4 | DevOps Engineer | kimi-k2.5 |
| SIGNAL | T4 | Observability Eng | kimi-k2.5 |
| INK | T4 | Technical Writer | kimi-k2.5 |

## Self-Evolution: How It Works

### ECHO — Scoring After Every Run
After each agent execution, ECHO scores the output across 5 dimensions:

| Dimension | Weight | Meaning |
|-----------|--------|---------|
| Quality | 30% | Technically correct and well-structured? |
| Completeness | 25% | Did it cover everything required? |
| Contract Adherence | 20% | Did it follow the API/spec format? |
| Efficiency | 15% | Is it lean, no unnecessary complexity? |
| Innovation | 10% | Did it go beyond the minimum? |

### DARWIN — Prompt Evolution
After every 5 runs, DARWIN checks fitness scores:
- Fitness ≥ 7.5 → agent is healthy, no action needed
- Fitness < 7.5 → DARWIN triggers, reads weak dimensions from ECHO
- DARWIN generates an improved system prompt targeting the weak spots
- New genome (version N+1) replaces the old one immediately
- The team's performance improves with every project

### MEMORIA — Persistent Memory
SQLite database (`memoria.db`) storing:
- **agent_genomes** — every prompt version, fitness score, parent lineage
- **echo_reports** — every run scored across 5 dimensions
- **evolution_records** — every mutation event with accept/reject outcome

## File Structure

```
agent-command/
├── main.py              ← CLI entry point
├── api_server.py        ← FastAPI HTTP server + dashboard
├── graph.py             ← LangGraph pipeline assembly
├── state.py             ← Shared state TypedDict schema
├── config.py            ← Models, thresholds, weights
├── pyproject.toml       ← pip-installable package config
├── MANIFEST.in          ← Non-editable install file list
├── requirements.txt      ← Legacy pip requirements
├── .env.example         ← Environment variable template
├── frontend/
│   ├── index.html       ← AgentCraft SPA entry
│   ├── styles.css       ← UI styles
│   ├── app.js           ← Frontend JavaScript
│   └── __init__.py
├── agents/
│   ├── base.py          ← BaseAgent (genome + ECHO + rate limiting)
│   └── team.py          ← All 13 agent classes
└── heart/
    ├── memoria.py       ← SQLite persistence layer
    ├── echo.py          ← Scoring agent
    └── darwin.py        ← Evolution engine
```
