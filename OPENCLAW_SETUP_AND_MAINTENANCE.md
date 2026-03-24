# AGENT COMMAND — OpenClaw Setup, Deployment & Maintenance Guide
# For Ayham's self-hosted server at 192.168.50.142 (Sharjah/Dubai)
# Stack: Docker + Cloudflare Tunnel + n8n scheduler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

---

## SECTION 1 — OPENCLAW SETUP PROMPT
### Paste this into OpenClaw to trigger full local installation

---

```
You are a senior DevOps + Python engineer setting up a LangGraph AI agent
team system called "Agent Command" on a self-hosted Ubuntu server.

Your task: set up this project from scratch, end to end, ready to run.

=== SYSTEM CONTEXT ===
- Host: Ubuntu server (local LAN at 192.168.50.142)
- Docker and Docker Compose are already installed
- Cloudflare Tunnel is already running under domain cyberx.cfd
- n8n is already running at http://192.168.50.142:5678
- Python 3.11+ is available
- The project zip file is at: ~/agent_command.zip

=== STEP 1: EXTRACT PROJECT ===
cd ~ && unzip -o agent_command.zip -d agent_command_project
cd agent_command_project/agent_command

=== STEP 2: CREATE VIRTUAL ENVIRONMENT ===
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

=== STEP 3: CONFIGURE ENVIRONMENT ===
cp .env.example .env

# Edit .env — set your real Anthropic API key:
# ANTHROPIC_API_KEY=sk-ant-YOUR-KEY-HERE
# MEMORIA_DB_PATH=./memoria.db

=== STEP 4: VERIFY INSTALLATION ===
python -c "
from state import AgentState
from agents.team import Nexus, Prism, Atlas, Pixel, Forge, Vault, Cipher, Weave, Probe, Lens, Launch, Signal, Ink
from heart.memoria import Memoria
from heart.echo import Echo
from heart.darwin import Darwin
from graph import build_graph, create_initial_state
print('✓ Agent Command ready')
"

=== STEP 5: INITIALIZE MEMORIA DATABASE ===
python -c "
import asyncio
from heart.memoria import Memoria
async def init():
    m = Memoria()
    await m.initialize()
    print('✓ MEMORIA database initialized at ./memoria.db')
asyncio.run(init())
"

=== STEP 6: RUN YOUR FIRST BUILD ===
python main.py "Build a simple REST API with authentication and PostgreSQL"

=== STEP 7: CHECK TEAM HEALTH ===
python main.py --health

=== STEP 8: DOCKERIZE (for persistent production use) ===
Create a Dockerfile:

cat > Dockerfile << 'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data
ENV MEMORIA_DB_PATH=/data/memoria.db
VOLUME ["/data"]
ENTRYPOINT ["python", "main.py"]
CMD ["--health"]
EOF

Build and run:
docker build -t agent-command:latest .
docker run -it --rm \
  -v $(pwd)/data:/data \
  -e ANTHROPIC_API_KEY=sk-ant-YOUR-KEY \
  agent-command:latest \
  "Build a SaaS product for UAE construction companies"

=== STEP 9: ADD TO DOCKER COMPOSE (alongside n8n) ===
Add this service to your existing docker-compose.yml:

  agent-command:
    image: agent-command:latest
    container_name: agent_command
    restart: unless-stopped
    volumes:
      - ./agent_command_data:/data
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - MEMORIA_DB_PATH=/data/memoria.db
    networks:
      - your_existing_network

=== STEP 10: EXPOSE VIA CLOUDFLARE TUNNEL (optional) ===
# Add a simple FastAPI wrapper so you can trigger builds via HTTP:
# Then expose via Cloudflare Tunnel under agents.cyberx.cfd

pip install fastapi uvicorn

Create api_server.py — see SECTION 3 of this guide below.

=== VERIFICATION CHECKLIST ===
[ ] .env file has real ANTHROPIC_API_KEY
[ ] memoria.db created successfully
[ ] python main.py --health shows 13 agents
[ ] First build completes without error
[ ] Docker image builds successfully
[ ] Docker volume mounts correctly (memoria.db persists)
```

---

## SECTION 2 — N8N SCHEDULER WORKFLOWS
### Import these into your n8n at 192.168.50.142:5678

---

### WORKFLOW A — Daily Evolution Trigger
**Purpose:** Every day at 3:00 AM UAE time (UTC+4), force Darwin to evolve
any agent below fitness threshold. Keeps the team improving without you
having to think about it.

```json
{
  "name": "Agent Command — Daily Evolution",
  "nodes": [
    {
      "name": "Cron Trigger",
      "type": "n8n-nodes-base.cron",
      "parameters": {
        "triggerTimes": {
          "item": [{ "hour": 23, "minute": 0 }]
        }
      }
    },
    {
      "name": "Run Darwin Evolution",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": {
        "command": "cd ~/agent_command_project/agent_command && source .venv/bin/activate && python main.py --evolve 2>&1"
      }
    },
    {
      "name": "Send Telegram/Slack Report",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "https://YOUR_WEBHOOK",
        "method": "POST",
        "body": "={{ 'Daily Evolution Report:\n' + $json.stdout }}"
      }
    }
  ]
}
```

**Cron schedule:** `0 23 * * *` (UTC) = 3:00 AM Dubai time
**Command to run:**
```bash
cd ~/agent_command_project/agent_command
source .venv/bin/activate
python main.py --evolve >> ~/logs/agent_command_evolution.log 2>&1
```

---

### WORKFLOW B — Weekly Health Report
**Purpose:** Every Sunday at 9:00 AM UAE time, generate and send a full
team health report showing fitness scores, run counts, genome versions.

**Cron schedule:** `0 5 * * 0` (UTC) = 9:00 AM Dubai Sunday
**Command to run:**
```bash
cd ~/agent_command_project/agent_command
source .venv/bin/activate
python main.py --health >> ~/logs/agent_command_health.log 2>&1
```

---

### WORKFLOW C — Performance Alert Trigger
**Purpose:** After every build, check if any agent dropped below fitness 5.0.
If yes, immediately trigger force evolution for that agent and notify.

**Trigger:** Webhook (call from main.py post-build)
**Logic:**
```bash
cd ~/agent_command_project/agent_command
source .venv/bin/activate
python -c "
import asyncio, json
from heart.memoria import Memoria
import config

async def check_alerts():
    m = Memoria()
    await m.initialize()
    health = await m.get_team_health()
    alerts = {k: v for k, v in health.items() if v['fitness'] < 5.0}
    if alerts:
        print(json.dumps({'alert': True, 'agents': alerts}))
        # Trigger immediate evolution for struggling agents
        from heart.darwin import Darwin
        from heart.echo import Echo
        echo = Echo(m)
        darwin = Darwin(m)
        for agent_id in alerts:
            await darwin.force_evolve(agent_id)
            print(f'Force evolved {agent_id}')
    else:
        print(json.dumps({'alert': False, 'message': 'All agents healthy'}))

asyncio.run(check_alerts())
"
```

---

### WORKFLOW D — Monthly Genome Archive
**Purpose:** First day of each month, export all current genomes to a
timestamped JSON backup. Lets you roll back if an evolution goes wrong.

**Cron schedule:** `0 0 1 * *` (midnight on 1st of month)
**Command to run:**
```bash
cd ~/agent_command_project/agent_command
source .venv/bin/activate
python -c "
import asyncio, json
from datetime import datetime
from heart.memoria import Memoria

async def archive():
    m = Memoria()
    await m.initialize()
    import config
    archive = {}
    for agent_id in config.AGENT_TIERS.keys():
        genome = await m.get_active_genome(agent_id)
        history = await m.get_genome_history(agent_id)
        archive[agent_id] = {
            'active_genome': genome,
            'full_history': history,
        }
    filename = f'genome_archive_{datetime.now().strftime(\"%Y%m%d\")}.json'
    with open(f'~/agent_command_backups/{filename}', 'w') as f:
        json.dump(archive, f, indent=2)
    print(f'✓ Archive saved: {filename}')

asyncio.run(archive())
"
```

---

## SECTION 3 — HTTP API WRAPPER
### FastAPI server so n8n + Cloudflare Tunnel can trigger builds remotely

```python
# api_server.py — paste this into your project root
# Run: uvicorn api_server:app --host 0.0.0.0 --port 8765

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import asyncio
import uuid
from datetime import datetime

from heart.memoria import Memoria
from heart.echo import Echo
from heart.darwin import Darwin
from graph import build_graph, create_initial_state
import config

app = FastAPI(title="Agent Command API", version="1.0.0")

# In-memory job tracker
jobs = {}

class BuildRequest(BaseModel):
    intent: str
    needs_ai: bool = False

class JobStatus(BaseModel):
    job_id: str
    status: str
    created_at: str
    result: dict | None = None

async def _run_build_job(job_id: str, intent: str, needs_ai: bool):
    jobs[job_id]["status"] = "running"
    try:
        memoria = Memoria()
        await memoria.initialize()
        echo = Echo(memoria)
        darwin = Darwin(memoria)
        graph = build_graph(memoria, echo, darwin)
        state = create_initial_state(intent, needs_ai)
        final_state = await graph.ainvoke(state)
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["result"] = {
            "quality_gate_passed": final_state.get("quality_gate_passed"),
            "final_report": final_state.get("final_report"),
            "echo_count": len(final_state.get("echo_reports", [])),
        }
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["result"] = {"error": str(e)}

@app.post("/build")
async def trigger_build(req: BuildRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "queued", "created_at": datetime.utcnow().isoformat(), "result": None}
    background_tasks.add_task(_run_build_job, job_id, req.intent, req.needs_ai)
    return {"job_id": job_id, "status": "queued"}

@app.get("/job/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]

@app.get("/health")
async def team_health():
    memoria = Memoria()
    await memoria.initialize()
    return await memoria.get_team_health()

@app.post("/evolve")
async def force_evolve():
    memoria = Memoria()
    await memoria.initialize()
    echo = Echo(memoria)
    darwin = Darwin(memoria)
    records = await darwin.evolve_team()
    return {"evolved": len(records), "agents": [r["agent_id"] for r in records]}

@app.get("/history/{agent_id}")
async def agent_history(agent_id: str):
    memoria = Memoria()
    await memoria.initialize()
    return await memoria.get_evolution_history(agent_id.upper())
```

**Run the API:**
```bash
uvicorn api_server:app --host 0.0.0.0 --port 8765 --reload
```

**Add to Cloudflare Tunnel config (~/.cloudflared/config.yml):**
```yaml
ingress:
  - hostname: agents.cyberx.cfd
    service: http://localhost:8765
  # ... your existing routes
```

**Call from n8n HTTP Request node:**
```
POST https://agents.cyberx.cfd/build
Body: { "intent": "Build a Bannaa contractor onboarding module", "needs_ai": true }
```

---

## SECTION 4 — IMPROVEMENT ROADMAP
### What to build next to make the system stronger over time

---

### PHASE 2 IMPROVEMENTS (Week 1-2)

**1. Add agent-to-agent feedback loops**
```python
# In quality_gate node, pass PROBE's bug report back to FORGE:
state["backend_code"] += f"\n\n# PROBE BUG REPORT:\n{state['test_suite'][:500]}"
# Then re-invoke FORGE with the bug context
```

**2. Add human-in-the-loop checkpoint**
```python
# After ATLAS produces architecture, pause and ask:
# "ATLAS proposes Next.js + PostgreSQL. Approve? [y/n/modify]"
# Saves you from running an expensive build on wrong assumptions
```

**3. Add per-project memory context**
```python
# Give NEXUS access to previous project summaries from MEMORIA
# So "iterate on Bannaa" gives NEXUS full context of what was built before
```

**4. Enable true parallel execution**
```python
# Use LangGraph's Send API for genuine parallel Phase 2 execution:
from langgraph.types import Send
def fan_out_build(state):
    return [Send("pixel", state), Send("forge", state), Send("vault", state)]
```

---

### PHASE 3 IMPROVEMENTS (Month 1)

**5. Add SCOUT — Research Agent**
```python
# Before PRISM runs, SCOUT searches for:
# - Competitor products
# - Relevant open source tools
# - UAE regulatory requirements
# - Best practices for the tech stack
# Injects research context into PRISM's prompt
```

**6. Add HERALD — Stakeholder Agent**
```python
# After INK runs, HERALD produces:
# - LinkedIn post announcing the product
# - Investor-ready one-pager
# - Client demo script
# Useful for Bannaa-style products you're pitching
```

**7. Multi-model A/B testing for genomes**
```python
# When DARWIN evolves a prompt, run both old and new genome
# on the next 3 builds, compare ECHO scores, keep the winner
# This is true natural selection — not just mutation
```

**8. DARWIN learns from patterns across agents**
```python
# If FORGE consistently scores low on security AND CIPHER finds issues,
# DARWIN should evolve FORGE's security patterns, not just FORGE's completeness
# Cross-agent weakness pattern detection
```

---

### PHASE 4 IMPROVEMENTS (Month 2-3)

**9. Connect to your actual codebase (Claude Code integration)**
```python
# Instead of generating code as text, LAUNCH actually:
# - Creates a real git repo
# - Commits each agent's output as separate commits
# - Opens a PR with LENS's review
# - Triggers actual CI/CD
```

**10. Bannaa-specialized genomes**
```python
# Create specialized genome variants for UAE/GCC context:
# PRISM_GULF: knows UAE regulations, Arabic UX patterns, SaaS pricing norms
# ATLAS_GULF: defaults to Cloudflare + self-hosted stack matching your infra
# FORGE_GULF: knows UAE payment gateways (PayTabs, Telr), e-invoicing
```

---

## SECTION 5 — MAINTENANCE CHEATSHEET
### Quick commands for day-to-day operation

```bash
# ── Daily ───────────────────────────────────────────────
python main.py --health               # Team fitness dashboard
python main.py --evolve               # Trigger evolution for weak agents

# ── Per Build ───────────────────────────────────────────
python main.py "Your intent here"     # Run a full build
python main.py "AI feature" --ai      # Force WEAVE activation

# ── Investigation ───────────────────────────────────────
python main.py --history FORGE        # See FORGE's prompt evolution
python main.py --history PIXEL        # See PIXEL's evolution
python main.py --interactive          # REPL mode (best for iteration)

# ── Database ────────────────────────────────────────────
sqlite3 memoria.db "SELECT agent_id, AVG(composite_score) FROM echo_reports GROUP BY agent_id ORDER BY 2 DESC;"
sqlite3 memoria.db "SELECT agent_id, version, fitness_score, mutation_notes FROM agent_genomes WHERE is_active=1;"
sqlite3 memoria.db "SELECT * FROM evolution_records ORDER BY timestamp DESC LIMIT 10;"

# ── Backups ─────────────────────────────────────────────
cp memoria.db memoria_backup_$(date +%Y%m%d).db

# ── Reset an agent (go back to genesis prompt) ──────────
sqlite3 memoria.db "UPDATE agent_genomes SET is_active=0 WHERE agent_id='FORGE'; UPDATE agent_genomes SET is_active=1 WHERE agent_id='FORGE' AND version=0;"
```

---

## SECTION 6 — OPENCLAW SKILL PROMPT
### Add this to OpenClaw as a persistent skill called "agent-command-ops"

```
You are the operations manager for Agent Command, a 13-agent LangGraph AI
development team running on Ayham's self-hosted server (192.168.50.142).

SYSTEM:
- Project: ~/agent_command_project/agent_command
- Venv: .venv (always activate before running)
- DB: memoria.db (SQLite — never delete)
- Scheduler: n8n at 192.168.50.142:5678
- Exposure: Cloudflare Tunnel at cyberx.cfd

YOUR JOB when asked to "run a build" or "build something":
1. cd to project directory
2. Activate venv
3. Run: python main.py "<intent>" [--ai if AI features needed]
4. Wait for completion
5. Report: quality gate result, avg ECHO score, any evolution events

YOUR JOB when asked to "check team health":
1. Run: python main.py --health
2. Report which agents are below 7.5 fitness
3. Suggest force evolution for any agent below 6.0

YOUR JOB when asked to "improve an agent" or "evolve FORGE":
1. Run: python main.py --history <AGENT>  (show what's been tried)
2. Run: python -c "...force_evolve(agent_id)..."  (trigger evolution)
3. Run: python main.py --health  (confirm fitness updated)

YOUR JOB when asked to "maintain the system":
1. Check MEMORIA DB size (warn if > 500MB)
2. Archive genomes if > 10 versions per agent
3. Run evolution for all agents below threshold
4. Verify n8n workflows are active
5. Verify Cloudflare Tunnel connectivity

IMPORTANT RULES:
- Never delete memoria.db — it contains all accumulated wisdom
- Always backup memoria.db before any major change
- If an agent's evolved prompt performs worse (fitness drops), revert:
  sqlite3 memoria.db "UPDATE agent_genomes SET is_active=0 WHERE agent_id='X' AND is_active=1; UPDATE agent_genomes SET is_active=1 WHERE agent_id='X' AND version=(SELECT MAX(version)-1 FROM agent_genomes WHERE agent_id='X');"
- ECHO and DARWIN are always running silently — you don't need to invoke them manually
```

---
*Agent Command — built for Ayham's self-hosted AI infrastructure*
*Server: 192.168.50.142 | Tunnel: cyberx.cfd | Scheduler: n8n*
