# AGENT COMMAND 🧠
### A self-evolving AI software development team built on LangGraph

> You speak. NEXUS listens. 13 agents build. ECHO watches. DARWIN evolves.

---

## Architecture

```
YOU
 │  (plain language)
 ▼
NEXUS (T0 — Commander)
 │  Decomposes intent → execution plan
 ▼
┌─ PHASE 1: STRATEGY ─────────────────────────────────┐
│  PRISM → ATLAS                                       │
│  (PRD) → (Architecture + API Contract + Schema)      │
└─────────────────────────────────────────────────────┘
 ▼
┌─ PHASE 2: BUILD (parallel) ─────────────────────────┐
│  PIXEL   → frontend code                            │
│  FORGE   → backend code                             │
│  VAULT   → database migrations                      │
│  CIPHER  → security audit                           │
│  WEAVE   → AI modules (conditional)                 │
└─────────────────────────────────────────────────────┘
 ▼
┌─ PHASE 3: QUALITY GATE ─────────────────────────────┐
│  PROBE  → test suite + coverage                     │
│  LENS   → code review + standards                   │
│  ↓  Both must PASS — else retry or escalate         │
└─────────────────────────────────────────────────────┘
 ▼
┌─ PHASE 4: SHIP ─────────────────────────────────────┐
│  LAUNCH → Dockerfile, CI/CD, deployment             │
│  SIGNAL → logging, metrics, alerts                  │
│  INK    → README, API docs, user guide              │
└─────────────────────────────────────────────────────┘
 ▼
┌─ HEART: SELF-EVOLUTION ─────────────────────────────┐
│  ECHO   → scores every agent run (5 dimensions)     │
│  DARWIN → reads scores, mutates weak prompts        │
│  MEMORIA→ persists all genomes + history (SQLite)   │
└─────────────────────────────────────────────────────┘
```

## The Heart & Soul

### MEMORIA (Long-term Memory)
SQLite database that persists across sessions:
- **agent_genomes** — every prompt version ever generated, with fitness scores
- **echo_reports** — every agent invocation scored on 5 dimensions
- **evolution_records** — every Darwin mutation event with accept/reject outcome

### ECHO (Tracking Agent)
After every agent execution, ECHO scores the output:
| Dimension | Weight | Meaning |
|-----------|--------|---------|
| Quality | 30% | Is the output technically correct? |
| Completeness | 25% | Did it cover everything? |
| Contract Adherence | 20% | Did it respect the input format? |
| Efficiency | 15% | Is it lean and well-structured? |
| Innovation | 10% | Did it go beyond the minimum? |

Weights are tier-specific — security agents weight contract adherence higher, strategy agents weight innovation more.

### DARWIN (Evolution Engine)
After every N runs, Darwin checks agent fitness:
1. If fitness < threshold (7.5/10), Darwin triggers
2. It reads ECHO's dimensional breakdown to find **weak dimensions**
3. It calls Claude Opus with the current prompt + weakness data
4. Claude generates an **improved system prompt** targeting the weak spots
5. New genome (version N+1) is saved to MEMORIA
6. The new genome replaces the old one for all future runs
7. Fitness is tracked on the new genome to measure improvement

This means agents that struggle to be complete get prompts that emphasize completeness. Agents that write insecure code get security-focused prompt additions. **The team gets better with every project.**

## Setup

```bash
git clone <this-repo>
cd agent_command
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add your MOONSHOT_API_KEY (or KIMI_API_KEY)
```

## Usage

```bash
# Build something
python main.py "Build a SaaS for UAE construction tenders"

# Build with AI features (activates WEAVE)
python main.py "Build a document Q&A system for construction BOQs" --ai

# Check team health / fitness scores
python main.py --health

# Force evolve all agents now (don't wait for threshold)
python main.py --evolve

# See an agent's evolution history
python main.py --history FORGE

# Interactive REPL — keep building in one session
python main.py --interactive
```

### Interactive Mode Commands
```
/health              → team fitness dashboard
/evolve              → force evolve all agents
/history <AGENT>     → show agent's evolution history
/quit                → exit
```

## Agent Roster

| Agent | Tier | Role | Model |
|-------|------|------|-------|
| NEXUS | T0 | Orchestrator | claude-opus |
| PRISM | T1 | Product Strategy | claude-sonnet |
| ATLAS | T1 | System Architecture | claude-opus |
| PIXEL | T2 | Frontend Engineer | claude-sonnet |
| FORGE | T2 | Backend Engineer | claude-sonnet |
| VAULT | T2 | Database Architect | claude-haiku |
| CIPHER | T2 | Security Engineer | claude-opus |
| WEAVE | T2 | AI/ML Engineer | claude-opus |
| PROBE | T3 | QA Engineer | claude-sonnet |
| LENS | T3 | Code Reviewer | claude-opus |
| LAUNCH | T4 | DevOps Engineer | claude-sonnet |
| SIGNAL | T4 | Observability Eng | claude-haiku |
| INK | T4 | Technical Writer | claude-sonnet |

## Evolution Example

After 5 runs of FORGE with fitness 6.2/10:
```
DARWIN: Evolution triggered for FORGE — fitness 6.20 < 7.50
DARWIN: Weak dimensions: contract_adherence (5.1), completeness (5.8), efficiency (6.0)
DARWIN: Generating improved prompt...
DARWIN: ✓ Evolved FORGE v0 → v1
DARWIN: Notes: Added explicit endpoint implementation checklist.
        Strengthened input validation requirements.
        Added streaming response pattern for large operations.
```

The new prompt is immediately active for the next build.

## File Structure

```
agent_command/
├── main.py              ← Entry point + CLI
├── graph.py             ← LangGraph pipeline
├── state.py             ← Shared state schema
├── config.py            ← Models, thresholds, weights
├── requirements.txt
├── .env.example
├── agents/
│   ├── base.py          ← BaseAgent (genome + ECHO integration)
│   └── team.py          ← All 13 agents
└── heart/
    ├── memoria.py        ← SQLite persistence layer
    ├── echo.py           ← Tracking + scoring agent
    └── darwin.py         ← Evolution engine
```
