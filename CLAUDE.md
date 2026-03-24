# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agent Command is a self-evolving AI software development team built on LangGraph. It orchestrates 13 agents (T0-T4 tiers) that receive a human's product intent in plain language and autonomously build complete software systems.

- **Language**: Python 3.14
- **Framework**: LangGraph (stateful graph-based agent orchestration)
- **LLM Provider**: Kimi/Moonshot (OpenAI-compatible API, model `kimi-k2.5`)
- **Database**: SQLite via `aiosqlite` for persistent agent memory
- **Observability**: Langfuse (optional), `pipeline_events.jsonl`
- **Entry point**: `main.py`

## Architecture

### Build Pipeline (4 phases)
```
START → nexus → prism + atlas → [PHASE 2: parallel build] → probe + lens → quality_gate → [PASS: launch → signal → ink | FAIL: retry/escalate] → END
```

### Agent Tiers
- **T0**: NEXUS — orchestrator, decomposes intent into execution plan
- **T1**: PRISM (product strategy), ATLAS (architecture)
- **T2**: PIXEL (frontend), FORGE (backend), VAULT (database), CIPHER (security), WEAVE (AI/ML, conditional)
- **T3**: PROBE (QA), LENS (code review)
- **T4**: LAUNCH (DevOps), SIGNAL (observability), INK (technical writing)

### Self-Evolution System (Heart)
Each agent's "intelligence" is a **versioned genome** (system prompt) stored in SQLite. Three modules form a feedback loop:
- **ECHO** (`heart/echo.py`) — scores every agent run on 5 dimensions (quality 30%, completeness 25%, contract adherence 20%, efficiency 15%, innovation 10%)
- **DARWIN** (`heart/darwin.py`) — after every 5 runs with fitness < 7.5, generates an improved prompt targeting weak dimensions
- **MEMORIA** (`heart/memoria.py`) — SQLite persistence for genomes, echo reports, evolution records

### Key Files
| File | Role |
|------|------|
| `main.py` | Entry point + CLI (`boot`, `run_build`, `--health`, `--evolve`, `--history`, `--interactive`) |
| `graph.py` | LangGraph StateGraph assembly — wires all nodes + conditional edges |
| `state.py` | `AgentState` TypedDict — all keys flowing through the graph |
| `config.py` | Central config — API keys, model assignments, temperature per agent, ECHO weights, thresholds |
| `agents/base.py` | `BaseAgent` — genome loading, LLM calls, ECHO scoring, rate limiting, Langfuse tracing |
| `agents/team.py` | All 13 agent subclasses — each overrides `_build_prompt()` and `_parse_output()` |

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set MOONSHOT_API_KEY (KIMI_API_KEY)

# Run a build
python main.py "Build a SaaS for UAE construction tenders"
python main.py "Build a document Q&A system" --ai   # forces WEAVE activation

# Health/fitness dashboard
python main.py --health

# Force evolve all agents
python main.py --evolve

# Show evolution history for an agent
python main.py --history FORGE

# Interactive REPL
python main.py --interactive

# Targeted evolution
python main.py --evolve-agents FORGE PIXEL
```

## Design Decisions

- **Genome-based agents**: Each agent's behavior is its system prompt stored in SQLite. DARWIN mutates the prompt, not the code.
- **Tier-weighted scoring**: ECHO uses different dimension weights per tier (T0/T1 weight innovation higher; T2/T3 weight contract adherence higher).
- **Rate limiting**: `KimiRateLimiter` in `base.py` implements sliding-window concurrency + RPM + TPM + TPD limiting.
- **Conditional execution**: WEAVE only activates when AI keywords are detected or `--ai` flag is passed.
- **Async throughout**: All database, LLM, and analytics operations are async (`aiosqlite`, `openai.AsyncOpenAI`).
