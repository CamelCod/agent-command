# Agent Command Pipeline — Analytics Tracking Plan

## Overview
- **Tools**: Langfuse (traces + scores) + JSONL (pipeline events) + Grafana (visualization)
- **Last updated**: 2026-03-24

## Metrics Tracked

### 1. Agent Performance (per run)

| Metric | Source | Type |
|--------|--------|------|
| `agent_id` | EchoReport | dimension |
| `duration_ms` | Agent call | metric |
| `composite_score` | ECHO (0-10) | score |
| `score_quality` | ECHO (0-10) | score |
| `score_completeness` | ECHO (0-10) | score |
| `score_contract_adherence` | ECHO (0-10) | score |
| `score_efficiency` | ECHO (0-10) | score |
| `score_innovation` | ECHO (0-10) | score |
| `genome_version` | AgentGenome | dimension |
| `run_id` | AgentState | dimension |

### 2. Pipeline Phase Events

| Event | Properties |
|-------|-----------|
| `phase_started` | phase, timestamp |
| `phase_completed` | phase, agents[], duration_seconds |
| `agent_completed` | agent_id, trace_id, duration_ms, composite_score, genome_version |

### 3. Quality Gate

| Metric | Source |
|--------|--------|
| `probe_score` | PROBE agent |
| `lens_score` | LENS agent |
| `threshold_probe` | config: 7.0 |
| `threshold_lens` | config: 7.0 |
| `passed` | bool |
| `attempt` | retry number |
| `escalated` | bool |

### 4. Evolution Events

| Metric | Source |
|--------|--------|
| `agent_id` | DARWIN |
| `from_version` | Genome diff |
| `to_version` | Genome diff |
| `fitness_before` | ECHO rolling avg |
| `fitness_after` | ECHO new score |
| `accepted` | bool |

### 5. Build Summary

| Metric | Source |
|--------|--------|
| `total_duration_seconds` | wall clock |
| `total_agents` | count |
| `total_retries` | quality gate retries |
| `evolution_count` | DARWIN events |
| `passed` | quality gate passed |
| `escalated` | max retries reached |

---

## Backends

### Langfuse Scores
ECHO composite scores submitted as Langfuse scores on each trace.
```python
await analytics.emit_agent_completed(
    agent_id="NEXUS",
    trace_id="abc123",
    duration_ms=37400,
    echo_report=report,
)
```

### JSONL Pipeline Events
`./pipeline_events.jsonl` — append-only log for Grafana BI ingestion.
```json
{"event": "agent_completed", "timestamp": "...", "agent_id": "NEXUS", "duration_ms": 37400, "composite_score": 5.0}
{"event": "quality_gate", "timestamp": "...", "attempt": 2, "probe_score": 8.5, "lens_score": 7.5, "passed": true}
{"event": "build_completed", "timestamp": "...", "duration_seconds": 1602, "passed": true}
```

### Grafana Dashboard (recommended panels)
- **Agent Score Heatmap**: composite_score by agent_id over time
- **Phase Duration**: bar chart of phase durations
- **Quality Gate Trend**: probe/lens score per build
- **Evolution Events**: event log of genome mutations
- **Build Success Rate**: pass/fail/escalate over time

---

## Event Schema

```json
// agent_completed
{
  "event": "agent_completed",
  "timestamp": "2026-03-24T09:26:00Z",
  "agent_id": "NEXUS",
  "trace_id": "abc123",
  "duration_ms": 37400,
  "composite_score": 5.0,
  "tier": "T0",
  "genome_version": 0,
  "scores": {
    "quality": 5.0,
    "completeness": 5.0,
    "contract_adherence": 5.0,
    "efficiency": 5.0,
    "innovation": 5.0
  },
  "assessment": "..."
}

// quality_gate
{
  "event": "quality_gate",
  "timestamp": "2026-03-24T09:41:18Z",
  "attempt": 2,
  "probe_score": 8.0,
  "lens_score": 4.0,
  "threshold": 7.0,
  "passed": false,
  "retry_count": 1
}

// evolution
{
  "event": "evolution",
  "timestamp": "2026-03-24T09:51:01Z",
  "agent_id": "ATLAS",
  "from_version": 0,
  "to_version": 1,
  "fitness_before": 4.2,
  "fitness_after": 5.8,
  "accepted": true
}

// build_completed
{
  "event": "build_completed",
  "timestamp": "2026-03-24T09:55:00Z",
  "project_id": "4b275934",
  "duration_seconds": 1800,
  "passed": true,
  "escalation": false,
  "total_agents": 12,
  "total_retries": 1,
  "evolution_count": 2,
  "deliverables": {
    "prd": true, "architecture": true, "frontend_code": true,
    "backend_code": true, "database_migrations": true,
    "security_audit": true, "ai_modules": true, "test_suite": true,
    "deployment_config": true, "observability_config": true, "documentation": true
  }
}
```

---

## Next: Grafana Setup

To visualize pipeline_events.jsonl in Grafana:
1. Add JSONL file as a Grafana Infinity data source (or CSV/JSON plugin)
2. Or use `jq` to tail + parse: `jq -c '.phase_completed' pipeline_events.jsonl`
3. Import dashboard JSON from `./dashboards/pipeline.json` (to create)
