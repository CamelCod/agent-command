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
        # -------------------------------------------------------
        # FUNCTION: initialize
        # GOAL:     Create all MEMORIA tables if they don't exist.
        # INPUT:    None
        # OUTPUT:   None — creates tables and indexes in SQLite.
        # STEPS:
        #   1. Connect to SQLite database.
        #   2. Execute DDL for agent_genomes, echo_reports, evolution_records.
        #   3. Create indexes on agent_id and project_id for performance.
        #   4. Commit and close connection.
        # -------------------------------------------------------
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
                    score_contract_adherence REAL NOT NULL,
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
                    trigger         TEXT,
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
        # -------------------------------------------------------
        # FUNCTION: save_genome
        # GOAL:     Persist a new genome version for an agent.
        # INPUT:    genome (AgentGenome) — the genome to persist
        # OUTPUT:   None — writes to SQLite agent_genomes table.
        # STEPS:
        #   1. Deactivate any currently active genome for this agent.
        #   2. Insert the new genome as the active version.
        #   3. Commit transaction.
        # -------------------------------------------------------
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
        # -------------------------------------------------------
        # FUNCTION: get_active_genome
        # GOAL:     Retrieve the currently active genome for an agent.
        # INPUT:    agent_id (str)
        # OUTPUT:   Returns AgentGenome or None if no active genome exists.
        # STEPS:
        #   1. Query agent_genomes where agent_id matches and is_active=1.
        #   2. Fetch one row and map to AgentGenome TypedDict.
        #   3. Return None if no row found.
        # -------------------------------------------------------
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
        # -------------------------------------------------------
        # FUNCTION: get_genome_history
        # GOAL:     Retrieve all past genome versions for an agent.
        # INPUT:    agent_id (str), limit (int) — max versions to return
        # OUTPUT:   Returns List[AgentGenome], newest first.
        # STEPS:
        #   1. Query agent_genomes ordered by version DESC.
        #   2. Apply LIMIT to restrict results.
        #   3. Map each row to AgentGenome TypedDict.
        # -------------------------------------------------------
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
        # -------------------------------------------------------
        # FUNCTION: save_echo_report
        # GOAL:     Persist a completed ECHO scoring report to SQLite.
        # INPUT:    report (EchoReport) — the report to save
        # OUTPUT:   None — writes to echo_reports table.
        # STEPS:
        #   1. INSERT OR REPLACE into echo_reports with all fields.
        #   2. Commit transaction.
        # -------------------------------------------------------
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO echo_reports
                (run_id, agent_id, genome_version, project_id,
                 score_quality, score_completeness, score_contract_adherence,
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
        # -------------------------------------------------------
        # FUNCTION: get_recent_reports
        # GOAL:     Retrieve the most recent ECHO reports for an agent.
        # INPUT:    agent_id (str), limit (int) — max reports to return
        # OUTPUT:   Returns List[EchoReport], newest first.
        # STEPS:
        #   1. Query echo_reports filtered by agent_id, ordered by timestamp DESC.
        #   2. Apply LIMIT.
        #   3. Map each row to EchoReport TypedDict.
        # -------------------------------------------------------
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
                        score_contract_adherence=r["score_contract_adherence"],
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
        # -------------------------------------------------------
        # FUNCTION: get_agent_fitness
        # GOAL:     Compute the rolling average composite score for an agent.
        # INPUT:    agent_id (str), last_n (int) — number of recent runs to average
        # OUTPUT:   Returns float fitness score (0.0 to 10.0), defaults to 5.0.
        # STEPS:
        #   1. Query last N echo_reports for agent, ordered DESC.
        #   2. Compute AVG(composite_score).
        #   3. Return 5.0 if no reports found.
        # -------------------------------------------------------
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
        # -------------------------------------------------------
        # FUNCTION: get_weak_dimensions
        # GOAL:     Identify which scoring dimensions are dragging an agent's fitness down.
        # INPUT:    agent_id (str), last_n (int) — number of recent runs to analyse
        # OUTPUT:   Returns Dict[str, float] mapping dimension name to average score.
        # STEPS:
        #   1. Query AVG of each score column over last N reports.
        #   2. Return dict with keys: quality, completeness, contract_adherence,
        #      efficiency, innovation. Missing/None maps to 5.0.
        # -------------------------------------------------------
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT
                       AVG(score_quality)      as quality,
                       AVG(score_completeness) as completeness,
                       AVG(score_contract_adherence) as contract_adherence,
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
        # -------------------------------------------------------
        # FUNCTION: get_run_count
        # GOAL:     Count how many times an agent has been invoked.
        # INPUT:    agent_id (str)
        # OUTPUT:   Returns int count of echo_reports for this agent.
        # -------------------------------------------------------
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM echo_reports WHERE agent_id = ?",
                (agent_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    # ── Evolution Record Operations ──────────────────────────────────────────

    async def save_evolution_record(self, record: EvolutionRecord):
        # -------------------------------------------------------
        # FUNCTION: save_evolution_record
        # GOAL:     Persist a DARWIN evolution mutation event.
        # INPUT:    record (EvolutionRecord) — the evolution event to save
        # OUTPUT:   None — writes to evolution_records table.
        # STEPS:
        #   1. INSERT OR REPLACE into evolution_records with all fields.
        #   2. Commit transaction.
        # -------------------------------------------------------
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO evolution_records
                (evolution_id, agent_id, from_version, to_version,
                 trigger, weak_dimensions, fitness_before,
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
        # -------------------------------------------------------
        # FUNCTION: get_evolution_history
        # GOAL:     Retrieve all evolution events for an agent.
        # INPUT:    agent_id (str)
        # OUTPUT:   Returns List[EvolutionRecord], newest first.
        # STEPS:
        #   1. Query evolution_records filtered by agent_id, ordered DESC.
        #   2. Map each row to EvolutionRecord TypedDict.
        # -------------------------------------------------------
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
                        trigger=r["trigger"],
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
        # -------------------------------------------------------
        # FUNCTION: get_team_health
        # GOAL:     Build a health snapshot for the entire agent team.
        # INPUT:    None
        # OUTPUT:   Returns Dict[str, dict] keyed by agent_id with fitness, runs,
        #           genome_version, generation, and model.
        # STEPS:
        #   1. Iterate over all known agent IDs from config.
        #   2. For each agent, fetch fitness, run count, and active genome.
        #   3. Return aggregated health dict.
        # -------------------------------------------------------
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
