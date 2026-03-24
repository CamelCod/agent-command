"""
heart/memoria.py — The long-term memory of the agent team.

MEMORIA is the persistent SQLite store that holds:
  - Agent genomes (every prompt version ever generated)
  - Echo execution reports (every run, scored)
  - Darwin evolution records (every mutation event)

This is what allows agents to improve across sessions.
Without MEMORIA, every run starts from scratch.
With MEMORIA, agents accumulate wisdom over time.
"""

from __future__ import annotations
import json
import uuid
import aiosqlite
from datetime import datetime
from typing import List, Optional, Dict, Any

from state import AgentGenome, EchoReport, EvolutionRecord
import config


# ─────────────────────────────────────────────────────────────────────────────
#  MEMORIA Class
# ─────────────────────────────────────────────────────────────────────────────

class Memoria:
    """
    Persistent memory for the entire agent team.
    Stores genomes, execution reports, and evolution history across sessions.
    """

    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def initialize(self):
        """Create tables if they don't exist. Call once at startup."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                -- Agent genomes: the evolving DNA of each agent
                CREATE TABLE IF NOT EXISTS agent_genomes (
                    id           TEXT PRIMARY KEY,
                    agent_id     TEXT NOT NULL,
                    version      INTEGER NOT NULL,
                    generation   INTEGER NOT NULL DEFAULT 0,
                    system_prompt TEXT NOT NULL,
                    model        TEXT NOT NULL,
                    temperature  REAL NOT NULL,
                    fitness_score REAL NOT NULL DEFAULT 5.0,
                    is_active    INTEGER NOT NULL DEFAULT 1,
                    parent_version INTEGER,
                    mutation_notes TEXT,
                    created_at   TEXT NOT NULL,
                    UNIQUE(agent_id, version)
                );

                -- ECHO execution reports: every agent invocation scored
                CREATE TABLE IF NOT EXISTS echo_reports (
                    run_id        TEXT PRIMARY KEY,
                    agent_id      TEXT NOT NULL,
                    genome_version INTEGER NOT NULL,
                    project_id    TEXT NOT NULL,
                    score_quality        REAL NOT NULL,
                    score_completeness   REAL NOT NULL,
                    score_contract       REAL NOT NULL,
                    score_efficiency     REAL NOT NULL,
                    score_innovation     REAL NOT NULL,
                    composite_score      REAL NOT NULL,
                    assessment    TEXT,
                    suggestions   TEXT,     -- JSON array
                    duration_ms   INTEGER,
                    timestamp     TEXT NOT NULL
                );

                -- DARWIN evolution records: every prompt mutation event
                CREATE TABLE IF NOT EXISTS evolution_records (
                    evolution_id    TEXT PRIMARY KEY,
                    agent_id        TEXT NOT NULL,
                    from_version    INTEGER NOT NULL,
                    to_version      INTEGER NOT NULL,
                    trigger_reason  TEXT,
                    weak_dimensions TEXT,   -- JSON array
                    fitness_before  REAL,
                    fitness_after   REAL,
                    prompt_diff_summary TEXT,
                    accepted        INTEGER NOT NULL DEFAULT 0,
                    timestamp       TEXT NOT NULL
                );

                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_echo_agent ON echo_reports(agent_id);
                CREATE INDEX IF NOT EXISTS idx_echo_project ON echo_reports(project_id);
                CREATE INDEX IF NOT EXISTS idx_genome_agent ON agent_genomes(agent_id, is_active);
            """)
            await db.commit()

    # ── Genome Operations ────────────────────────────────────────────────────

    async def save_genome(self, genome: AgentGenome):
        """Persist a new genome version."""
        async with aiosqlite.connect(self.db_path) as db:
            # Deactivate old active genome for this agent
            await db.execute(
                "UPDATE agent_genomes SET is_active = 0 WHERE agent_id = ? AND is_active = 1",
                (genome["agent_id"],)
            )
            # Insert new genome
            await db.execute("""
                INSERT OR REPLACE INTO agent_genomes
                (id, agent_id, version, generation, system_prompt, model, temperature,
                 fitness_score, is_active, parent_version, mutation_notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                genome["agent_id"],
                genome["version"],
                genome["generation"],
                genome["system_prompt"],
                genome["model"],
                genome["temperature"],
                genome["fitness_score"],
                genome.get("parent_version"),
                genome.get("mutation_notes"),
                genome["created_at"],
            ))
            await db.commit()

    async def get_active_genome(self, agent_id: str) -> Optional[AgentGenome]:
        """Get the current active genome for an agent."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM agent_genomes WHERE agent_id = ? AND is_active = 1",
                (agent_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return AgentGenome(
                    agent_id=row["agent_id"],
                    system_prompt=row["system_prompt"],
                    model=row["model"],
                    temperature=row["temperature"],
                    version=row["version"],
                    generation=row["generation"],
                    fitness_score=row["fitness_score"],
                    created_at=row["created_at"],
                    parent_version=row["parent_version"],
                    mutation_notes=row["mutation_notes"],
                )

    async def get_genome_history(self, agent_id: str, limit: int = 10) -> List[AgentGenome]:
        """Get all genome versions for an agent, newest first."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM agent_genomes WHERE agent_id = ? ORDER BY version DESC LIMIT ?",
                (agent_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    AgentGenome(
                        agent_id=r["agent_id"],
                        system_prompt=r["system_prompt"],
                        model=r["model"],
                        temperature=r["temperature"],
                        version=r["version"],
                        generation=r["generation"],
                        fitness_score=r["fitness_score"],
                        created_at=r["created_at"],
                        parent_version=r["parent_version"],
                        mutation_notes=r["mutation_notes"],
                    )
                    for r in rows
                ]

    # ── Echo Report Operations ───────────────────────────────────────────────

    async def save_echo_report(self, report: EchoReport):
        """Persist a new ECHO scoring report."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO echo_reports
                (run_id, agent_id, genome_version, project_id,
                 score_quality, score_completeness, score_contract,
                 score_efficiency, score_innovation, composite_score,
                 assessment, suggestions, duration_ms, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report["run_id"],
                report["agent_id"],
                report["genome_version"],
                report["project_id"],
                report["score_quality"],
                report["score_completeness"],
                report["score_contract_adherence"],
                report["score_efficiency"],
                report["score_innovation"],
                report["composite_score"],
                report["assessment"],
                json.dumps(report["improvement_suggestions"]),
                report["duration_ms"],
                report["timestamp"],
            ))
            await db.commit()

    async def get_recent_reports(self, agent_id: str, limit: int = 20) -> List[EchoReport]:
        """Get the N most recent ECHO reports for an agent."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM echo_reports WHERE agent_id = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (agent_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    EchoReport(
                        run_id=r["run_id"],
                        agent_id=r["agent_id"],
                        genome_version=r["genome_version"],
                        project_id=r["project_id"],
                        score_quality=r["score_quality"],
                        score_completeness=r["score_completeness"],
                        score_contract_adherence=r["score_contract"],
                        score_efficiency=r["score_efficiency"],
                        score_innovation=r["score_innovation"],
                        composite_score=r["composite_score"],
                        assessment=r["assessment"],
                        improvement_suggestions=json.loads(r["suggestions"] or "[]"),
                        duration_ms=r["duration_ms"],
                        timestamp=r["timestamp"],
                    )
                    for r in rows
                ]

    async def get_agent_fitness(self, agent_id: str, last_n: int = 10) -> float:
        """Compute rolling average fitness score for an agent."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT AVG(composite_score) as avg_score FROM (
                       SELECT composite_score FROM echo_reports
                       WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?
                   )""",
                (agent_id, last_n)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] is not None else 5.0

    async def get_weak_dimensions(self, agent_id: str, last_n: int = 10) -> Dict[str, float]:
        """Get average score per dimension to identify what's dragging fitness down."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT
                       AVG(score_quality)      as quality,
                       AVG(score_completeness) as completeness,
                       AVG(score_contract)     as contract_adherence,
                       AVG(score_efficiency)   as efficiency,
                       AVG(score_innovation)   as innovation
                   FROM (
                       SELECT * FROM echo_reports WHERE agent_id = ?
                       ORDER BY timestamp DESC LIMIT ?
                   )""",
                (agent_id, last_n)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return {}
                return {
                    "quality":            row[0] or 5.0,
                    "completeness":       row[1] or 5.0,
                    "contract_adherence": row[2] or 5.0,
                    "efficiency":         row[3] or 5.0,
                    "innovation":         row[4] or 5.0,
                }

    async def get_run_count(self, agent_id: str) -> int:
        """Total number of times an agent has been invoked."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM echo_reports WHERE agent_id = ?",
                (agent_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    # ── Evolution Record Operations ──────────────────────────────────────────

    async def save_evolution_record(self, record: EvolutionRecord):
        """Persist a Darwin evolution event."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO evolution_records
                (evolution_id, agent_id, from_version, to_version,
                 trigger_reason, weak_dimensions, fitness_before,
                 fitness_after, prompt_diff_summary, accepted, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record["evolution_id"],
                record["agent_id"],
                record["from_version"],
                record["to_version"],
                record["trigger"],
                json.dumps(record["weak_dimensions"]),
                record["fitness_before"],
                record.get("fitness_after"),
                record["prompt_diff_summary"],
                1 if record["accepted"] else 0,
                record["timestamp"],
            ))
            await db.commit()

    async def get_evolution_history(self, agent_id: str) -> List[EvolutionRecord]:
        """Get full evolution history for an agent."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM evolution_records WHERE agent_id = ? ORDER BY timestamp DESC",
                (agent_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    EvolutionRecord(
                        evolution_id=r["evolution_id"],
                        agent_id=r["agent_id"],
                        from_version=r["from_version"],
                        to_version=r["to_version"],
                        trigger=r["trigger_reason"],
                        weak_dimensions=json.loads(r["weak_dimensions"] or "[]"),
                        fitness_before=r["fitness_before"],
                        fitness_after=r["fitness_after"],
                        prompt_diff_summary=r["prompt_diff_summary"],
                        accepted=bool(r["accepted"]),
                        timestamp=r["timestamp"],
                    )
                    for r in rows
                ]

    # ── Dashboard Helpers ────────────────────────────────────────────────────

    async def get_team_health(self) -> Dict[str, Any]:
        """Return a health snapshot of the entire agent team."""
        agents = list(config.AGENT_TIERS.keys())
        health = {}
        for agent_id in agents:
            fitness = await self.get_agent_fitness(agent_id)
            run_count = await self.get_run_count(agent_id)
            genome = await self.get_active_genome(agent_id)
            health[agent_id] = {
                "fitness": round(fitness, 2),
                "runs": run_count,
                "genome_version": genome["version"] if genome else 0,
                "generation": genome["generation"] if genome else 0,
                "model": genome["model"] if genome else config.AGENT_MODELS.get(agent_id),
            }
        return health
