"""Shared fixtures and configuration for E2E tests."""

import os
import time
from pathlib import Path
from typing import Generator

import pytest


# Paths to the actual kgs-bot and kgs-bot-monitor installations
KGS_BOT_PATH = Path("/workspace/Kgs-bot")
MONITOR_PATH = Path("/workspace/kgs-bot-monitor")

# Test bot configuration
TEST_BOT_ID = "test_bot"
TEST_RUN_DIR = Path("/workspace/kgs-bot-debug/run")


@pytest.fixture(scope="session")
def test_run_dir() -> Path:
    """Create and return the test run directory."""
    TEST_RUN_DIR.mkdir(exist_ok=True)
    return TEST_RUN_DIR


@pytest.fixture
def bot_id() -> str:
    """Return the test bot ID."""
    return TEST_BOT_ID


@pytest.fixture
def command_file(test_run_dir: Path, bot_id: str) -> Path:
    """Return path to command file."""
    return test_run_dir / f"{bot_id}_command.json"


@pytest.fixture
def result_file(test_run_dir: Path, bot_id: str) -> Path:
    """Return path to command result file."""
    return test_run_dir / f"{bot_id}_command_result.json"


@pytest.fixture
def state_file(test_run_dir: Path, bot_id: str) -> Path:
    """Return path to state file."""
    return test_run_dir / f"{bot_id}_state.json"


@pytest.fixture
def logs_dir() -> Path:
    """Return path to logs directory."""
    logs_dir = Path("/workspace/kgs-bot-debug/logs") / TEST_BOT_ID
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


@pytest.fixture
def kgs_bot_path() -> Path:
    """Return path to kgs-bot installation."""
    return KGS_BOT_PATH


@pytest.fixture
def monitor_path() -> Path:
    """Return path to kgs-bot-monitor installation."""
    return MONITOR_PATH


def pytest_configure(config):
    """Configure pytest with markers."""
    config.addinivalue_line(
        "markers", "phase1: Phase 1 tests (command/response protocol)"
    )
    config.addinivalue_line(
        "markers", "phase2: Phase 2 tests (observation flow)"
    )
    config.addinivalue_line(
        "markers", "phase3: Phase 3 tests (race conditions)"
    )
    config.addinivalue_line(
        "markers", "phase4: Phase 4 tests (error recovery)"
    )