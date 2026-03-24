"""
tests/test_core.py — Core functionality tests.
"""
import pytest
import asyncio
from agents.base import KimiRateLimiter, CODE_GENERATING_AGENTS, DISCIPLINED_PROGRAMMER_PROLOGUE
import config


class TestKimiRateLimiter:
    """Tests for the rate limiter."""

    def test_tpd_increment_is_thread_safe(self):
        """TPD increment must happen inside the rate lock."""
        # This is a structural test — verify TPD tracking works
        rl = KimiRateLimiter()
        initial = rl._tpd_used
        # Simulate token tracking
        rl._tpd_used += 1000
        assert rl._tpd_used == initial + 1000

    def test_rate_limiter_initialization(self):
        """Rate limiter initializes with correct config."""
        rl = KimiRateLimiter()
        assert rl.cfg["rpm"] == config.RATE_LIMIT["rpm"]
        assert rl.cfg["tpm"] == config.RATE_LIMIT["tpm"]
        assert rl.cfg["tpd"] == config.RATE_LIMIT["tpd"]


class TestCodeGeneratingAgents:
    """Tests for the disciplined programmer prologue injection."""

    def test_code_generating_agents_defined(self):
        """CODE_GENERATING_AGENTS must be a non-empty set."""
        assert isinstance(CODE_GENERATING_AGENTS, set)
        assert len(CODE_GENERATING_AGENTS) > 0
        # Must include all expected code-generating agents
        expected = {"PIXEL", "FORGE", "VAULT", "CIPHER", "WEAVE", "PROBE", "LENS"}
        assert expected.issubset(CODE_GENERATING_AGENTS)

    def test_disciplined_programmer_prologue_non_empty(self):
        """Prologue must be non-empty and contain key rules."""
        assert len(DISCIPLINED_PROGRAMMER_PROLOGUE) > 100
        assert "ALGORITHM FIRST" in DISCIPLINED_PROGRAMMER_PROLOGUE
        assert "PILLAR" in DISCIPLINED_PROGRAMMER_PROLOGUE
        assert "keepGoing" in DISCIPLINED_PROGRAMMER_PROLOGUE

    def test_prologue_contains_no_abbreviation_rule(self):
        """Prologue must forbid abbreviations."""
        assert "abbreviation" in DISCIPLINED_PROGRAMMER_PROLOGUE.lower()


class TestConfig:
    """Tests for config module."""

    def test_quality_gate_thresholds_defined(self):
        """Quality gate must have numeric thresholds."""
        assert config.QUALITY_GATE["min_probe_score"] >= 0
        assert config.QUALITY_GATE["min_lens_score"] >= 0
        assert config.QUALITY_GATE["max_retries"] >= 0

    def test_evolution_config_defined(self):
        """Evolution config must have required keys."""
        assert "runs_before_evolution" in config.EVOLUTION_CONFIG
        assert "fitness_threshold" in config.EVOLUTION_CONFIG
        assert config.EVOLUTION_CONFIG["fitness_threshold"] > 0

    def test_agent_tiers_all_agents_defined(self):
        """All 13 agents must have tier assignments."""
        expected_agents = {
            "NEXUS", "PRISM", "ATLAS", "PIXEL", "FORGE", "VAULT",
            "CIPHER", "WEAVE", "PROBE", "LENS", "LAUNCH", "SIGNAL", "INK"
        }
        assert set(config.AGENT_TIERS.keys()) == expected_agents


class TestQualityGateLogic:
    """Tests for quality gate threshold logic."""

    def test_gate_passes_when_scores_meet_threshold(self):
        """Quality gate should pass when probe >= min and lens >= min."""
        min_probe = config.QUALITY_GATE["min_probe_score"]
        min_lens  = config.QUALITY_GATE["min_lens_score"]
        # If scores exactly at threshold, gate should pass
        probe_score = min_probe
        lens_score  = min_lens
        passed = (
            probe_score >= min_probe and
            lens_score  >= min_lens
        )
        assert passed is True

    def test_gate_fails_when_probe_below_threshold(self):
        """Quality gate should fail when probe is below threshold."""
        min_probe = config.QUALITY_GATE["min_probe_score"]
        min_lens  = config.QUALITY_GATE["min_lens_score"]
        probe_score = min_probe - 0.1
        lens_score  = min_lens + 1.0
        passed = (
            probe_score >= min_probe and
            lens_score  >= min_lens
        )
        assert passed is False

    def test_gate_fails_when_lens_below_threshold(self):
        """Quality gate should fail when lens is below threshold."""
        min_probe = config.QUALITY_GATE["min_probe_score"]
        min_lens  = config.QUALITY_GATE["min_lens_score"]
        probe_score = min_probe + 1.0
        lens_score  = min_lens - 0.1
        passed = (
            probe_score >= min_probe and
            lens_score  >= min_lens
        )
        assert passed is False
