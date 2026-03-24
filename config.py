"""
config.py — Central configuration for the Agent Command system.
All model assignments, evolution thresholds, and scoring weights live here.
"""

import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
#  API Keys
# ─────────────────────────────────────────────
KIMI_API_KEY = os.getenv("MOONSHOT_API_KEY", os.getenv("KIMI_API_KEY", ""))
KIMI_BASE_URL = "https://api.moonshot.ai/v1"

# ─────────────────────────────────────────────
#  Rate Limiting (Kimi Moonshot)
# ─────────────────────────────────────────────
# Configure these based on your Kimi API plan limits
RATE_LIMIT = {
    "max_concurrency": int(os.getenv("KIMI_MAX_CONCURRENCY", 5)),
    "rpm": int(os.getenv("KIMI_RPM", 60)),           # Requests per minute
    "tpm": int(os.getenv("KIMI_TPM", 128000)),       # Tokens per minute
    "tpd": int(os.getenv("KIMI_TPD", 1000000)),      # Tokens per day
}

# ─────────────────────────────────────────────
#  Langfuse Tracing (Observability)
# ─────────────────────────────────────────────
LANGFUSE_CONFIG = {
    "public_key": os.getenv("LANGFUSE_PUBLIC_KEY", ""),
    "secret_key": os.getenv("LANGFUSE_SECRET_KEY", ""),
    "host": os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
    "enabled": bool(os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"),
    "flush_interval": 5,  # seconds
}

# ─────────────────────────────────────────────
#  Model Assignments per Agent
#  Using Kimi (Moonshot) via OpenAI-compatible API
# ─────────────────────────────────────────────
AGENT_MODELS: Dict[str, str] = {
    "NEXUS":  "kimi-k2.5",
    "PRISM":  "kimi-k2.5",
    "ATLAS":  "kimi-k2.5",
    "PIXEL":  "kimi-k2.5",
    "FORGE":  "kimi-k2.5",
    "VAULT":  "kimi-k2.5",
    "CIPHER": "kimi-k2.5",
    "WEAVE":  "kimi-k2.5",
    "PROBE":  "kimi-k2.5",
    "LENS":   "kimi-k2.5",
    "LAUNCH": "kimi-k2.5",
    "SIGNAL": "kimi-k2.5",
    "INK":    "kimi-k2.5",
    # Heart Agents
    "ECHO":   "kimi-k2.5",
    "DARWIN": "kimi-k2.5",
}

# ─────────────────────────────────────────────
#  Agent Temperature Settings
# ─────────────────────────────────────────────
AGENT_TEMPERATURES: Dict[str, float] = {
    "NEXUS":  0.3,   # Deterministic orchestration
    "PRISM":  0.7,   # Creative product thinking
    "ATLAS":  0.2,   # Precise architecture
    "PIXEL":  0.5,   # Balanced UI code
    "FORGE":  0.2,   # Precise backend code
    "VAULT":  0.1,   # Very precise schema design
    "CIPHER": 0.1,   # Zero ambiguity in security
    "WEAVE":  0.6,   # Creative AI solutions
    "PROBE":  0.2,   # Systematic testing
    "LENS":   0.3,   # Consistent code standards
    "LAUNCH": 0.2,   # Precise infra configs
    "SIGNAL": 0.1,   # Precise monitoring rules
    "INK":    0.5,   # Clear but engaging docs
    "ECHO":   0.1,   # Consistent scoring
    "DARWIN": 0.7,   # Creative prompt evolution
}

# ─────────────────────────────────────────────
#  Evolution (DARWIN) Settings
# ─────────────────────────────────────────────
EVOLUTION_CONFIG = {
    # After how many runs to trigger Darwin evolution check
    "runs_before_evolution": 5,
    # Minimum fitness score to avoid forced evolution
    "fitness_threshold": 7.5,
    # How many top-performing genomes to keep per agent (elitism)
    "elite_keep": 2,
    # Temperature boost for prompt mutation (exploration)
    "mutation_temperature": 0.85,
    # Max genome versions to store per agent
    "max_genome_history": 10,
    # Minimum score improvement to accept new genome (%)
    "improvement_threshold": 0.05,
}

# ─────────────────────────────────────────────
#  ECHO Scoring Dimensions + Weights
# ─────────────────────────────────────────────
ECHO_SCORING = {
    "dimensions": {
        "quality":            0.30,  # Is the output good?
        "completeness":       0.25,  # Did it cover everything asked?
        "contract_adherence": 0.20,  # Did it respect the input contract?
        "efficiency":         0.15,  # Was it lean and non-redundant?
        "innovation":         0.10,  # Did it go beyond the obvious?
    },
    # Weighting per tier (Tier 0/1 values strategy more; Tier 2 values precision)
    "tier_weights": {
        "T0": {"quality": 0.40, "completeness": 0.30, "contract_adherence": 0.15, "efficiency": 0.10, "innovation": 0.05},
        "T1": {"quality": 0.30, "completeness": 0.25, "contract_adherence": 0.20, "efficiency": 0.10, "innovation": 0.15},
        "T2": {"quality": 0.25, "completeness": 0.25, "contract_adherence": 0.30, "efficiency": 0.15, "innovation": 0.05},
        "T3": {"quality": 0.35, "completeness": 0.30, "contract_adherence": 0.25, "efficiency": 0.10, "innovation": 0.00},
        "T4": {"quality": 0.25, "completeness": 0.30, "contract_adherence": 0.30, "efficiency": 0.15, "innovation": 0.00},
    }
}

# ─────────────────────────────────────────────
#  Agent Tier Mapping
# ─────────────────────────────────────────────
AGENT_TIERS: Dict[str, str] = {
    "NEXUS":  "T0",
    "PRISM":  "T1",
    "ATLAS":  "T1",
    "PIXEL":  "T2",
    "FORGE":  "T2",
    "VAULT":  "T2",
    "CIPHER": "T2",
    "WEAVE":  "T2",
    "PROBE":  "T3",
    "LENS":   "T3",
    "LAUNCH": "T4",
    "SIGNAL": "T4",
    "INK":    "T4",
}

# ─────────────────────────────────────────────
#  Persistence
# ─────────────────────────────────────────────
DB_PATH = os.getenv("MEMORIA_DB_PATH", "./memoria.db")
GENOME_REGISTRY_PATH = os.getenv("GENOME_PATH", "./genomes/")

# ─────────────────────────────────────────────
#  Quality Gate Thresholds
# ─────────────────────────────────────────────
QUALITY_GATE = {
    "min_probe_score": 7.0,   # PROBE must score >= this to PASS
    "min_lens_score":  7.0,   # LENS must score >= this to PASS
    "max_retries":     2,     # Max rebuild cycles before human escalation
}
